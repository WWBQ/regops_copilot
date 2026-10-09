import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.api.auth import require_regops_user
from agent.app import app


USER_ID = "00000000-0000-0000-0000-000000000001"
CODING_ID = f"{USER_ID}_coding_11111111-1111-1111-1111-111111111111"
RISK_ID = f"{USER_ID}_11111111-1111-1111-1111-111111111111"


class CodingAgentApiTest(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[require_regops_user] = lambda: USER_ID
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()

    def test_cross_product_thread_is_rejected(self):
        with patch("agent.api.coding_agent.get_task") as get_task:
            response = self.client.get(f"/regops/coding-agent/threads/{RISK_ID}")
            self.assertEqual(response.status_code, 404)
            get_task.assert_not_called()
        with patch("agent.api.risk_agent.get_task") as get_task:
            response = self.client.get(f"/regops/agent/threads/{CODING_ID}")
            self.assertEqual(response.status_code, 404)
            get_task.assert_not_called()

    def test_coding_list_uses_its_own_prefix(self):
        with patch("agent.api.coding_agent.list_tasks", return_value=[]) as list_tasks:
            response = self.client.get("/regops/coding-agent/threads")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), [])
            list_tasks.assert_called_once_with(limit=50, owner_prefix=f"{USER_ID}_coding_")

    def test_risk_list_excludes_coding_prefix(self):
        with patch("agent.api.risk_agent.list_tasks", return_value=[]) as list_tasks:
            response = self.client.get("/regops/agent/threads")
            self.assertEqual(response.status_code, 200)
            list_tasks.assert_called_once_with(
                limit=50, owner_prefix=f"{USER_ID}_",
                exclude_prefix=f"{USER_ID}_coding_",
            )

    def test_existing_coding_thread_restores_checkpoint_messages(self):
        thread = {
            "thread_id": CODING_ID, "title": "修复测试", "latest_run_status": "completed",
            "created_at": "2026-10-09T00:00:00+00:00", "updated_at": "2026-10-09T00:01:00+00:00",
        }
        with patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.visible_checkpoint_messages", return_value=[
                {"message_id": "u1", "author": "user", "content": "分析测试"},
                {"message_id": "a1", "author": "agent", "content": "测试入口在 tests/"},
            ],
        ):
            response = self.client.get(f"/regops/coding-agent/threads/{CODING_ID}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["author"] for item in response.json()["messages"]], ["user", "agent"])

    def test_export_returns_zip_only_for_owned_completed_thread(self):
        thread = {"thread_id": CODING_ID, "latest_run_status": "completed", "sandbox_id": "sandbox-1"}
        with patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.export_project_zip", return_value=("demo", b"ZIP"),
        ) as export:
            response = self.client.get(f"/regops/coding-agent/threads/{CODING_ID}/export")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ZIP")
        self.assertEqual(response.headers["content-type"], "application/zip")
        export.assert_called_once_with(CODING_ID)

        with patch("agent.api.coding_agent.get_task") as get_task:
            response = self.client.get(f"/regops/coding-agent/threads/{RISK_ID}/export")
        self.assertEqual(response.status_code, 404)
        get_task.assert_not_called()

    def test_bound_sandbox_rejects_project_switch_before_writing_thread(self):
        thread = {"thread_id": CODING_ID, "sandbox_id": "sandbox-1", "sandbox_project": "demo"}
        with patch("agent.api.coding_agent.require_agent_model_id", return_value="fake-model"), patch(
            "agent.api.coding_agent.execution_backend", return_value="opensandbox",
        ), patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.selected_project", return_value="other",
        ), patch("agent.api.coding_agent.initialize_task_record") as initialize:
            response = self.client.post(
                f"/regops/coding-agent/threads/{CODING_ID}/stream-message",
                json={"content": "目标项目：/projects/other\n用户任务：修改代码", "model_id": "fake-model"},
            )
        self.assertEqual(response.status_code, 409)
        initialize.assert_not_called()

    def test_deleting_sandbox_thread_destroys_container_even_after_mode_change(self):
        with patch("agent.api.coding_agent.get_task", return_value={"sandbox_id": "sandbox-1"}), patch(
            "agent.api.coding_agent.destroy_sandbox_for_thread",
        ) as destroy, patch("agent.api.coding_agent.delete_task", return_value=True):
            response = self.client.delete(f"/regops/coding-agent/threads/{CODING_ID}")
        self.assertEqual(response.status_code, 204)
        destroy.assert_called_once_with(CODING_ID)

    def test_coding_stream_cannot_enter_financial_mode(self):
        thread = {
            "thread_id": CODING_ID, "title": "任务", "latest_run_status": "running",
            "created_at": "2026-10-09T00:00:00+00:00", "updated_at": "2026-10-09T00:01:00+00:00",
        }
        with patch("agent.api.coding_agent.require_agent_model_id", return_value="fake-model"), patch(
            "agent.api.coding_agent.initialize_task_record", return_value=CODING_ID,
        ), patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.run_coding_task", return_value={"final_answer": "已完成分析"},
        ) as run_task:
            response = self.client.post(
                "/regops/coding-agent/threads/stream-message",
                json={"content": "分析项目结构", "model_id": "fake-model"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: final_answer", response.text)
        self.assertIn("已完成分析", response.text)
        self.assertEqual(run_task.call_args.kwargs["prompt"], "分析项目结构")

    def test_coding_service_forces_domain_boundary(self):
        from agent.coding.service import run_coding_task

        with patch("agent.coding.service.run_agent_task", return_value={}) as runtime:
            run_coding_task(prompt="检查年报风险", thread_id=CODING_ID,
                            model_id="fake-model", event_sink=lambda *_: None)
        self.assertFalse(runtime.call_args.kwargs["allow_financial_audit"])
        self.assertFalse(runtime.call_args.kwargs["forced_financial_audit"])

    def test_selected_project_prompt_is_not_treated_as_workspace_listing(self):
        from agent.core.task_intent import is_workspace_listing_task

        prompt = "目标项目：/projects/demo\n用户任务：分析项目结构和测试入口"
        self.assertFalse(is_workspace_listing_task(prompt))

    def test_graph_factories_are_separate(self):
        from agent.server import get_agent

        config = {"configurable": {
            "thread_id": CODING_ID, "task_kind": "coding", "__is_for_execution__": True,
        }}
        with patch("agent.server.get_coding_agent", return_value="coding") as coding, patch(
            "agent.server.get_financial_agent", return_value="financial",
        ) as financial:
            self.assertEqual(get_agent(config), "coding")
            coding.assert_called_once()
            financial.assert_not_called()

        config["configurable"]["task_kind"] = "financial_audit"
        with patch("agent.server.get_coding_agent", return_value="coding") as coding, patch(
            "agent.server.get_financial_agent", return_value="financial",
        ) as financial:
            self.assertEqual(get_agent(config), "financial")
            financial.assert_called_once()
            coding.assert_not_called()


if __name__ == "__main__":
    unittest.main()
