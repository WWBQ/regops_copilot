import unittest
from types import SimpleNamespace
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

    def test_host_project_endpoints_are_removed(self):
        self.assertEqual(self.client.get("/regops/coding-agent/projects").status_code, 404)
        self.assertEqual(self.client.post(
            "/regops/coding-agent/projects", json={"name": "new-project"},
        ).status_code, 404)

    def test_create_sandbox_stays_in_coding_user_namespace(self):
        thread = {
            "thread_id": CODING_ID, "title": "AI Coding 会话", "latest_run_status": "idle",
            "sandbox_id": None,
        }
        after = {**thread, "sandbox_id": "sandbox-new"}
        with patch("agent.api.coding_agent.get_store") as get_store, patch(
            "agent.api.coding_agent.get_task", side_effect=[thread, after],
        ), patch("agent.api.coding_agent.execution_backend", return_value="opensandbox"), patch(
            "agent.api.coding_agent.ensure_sandbox_for_thread", return_value=SimpleNamespace(id="sandbox-new"),
        ), patch("agent.api.coding_agent.consume_workspace_notice", return_value=None):
            response = self.client.post("/regops/coding-agent/threads/sandbox")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["sandbox_created"])
        self.assertEqual(response.json()["thread"]["status"], "idle")
        created_id = get_store.return_value.upsert_thread.call_args.kwargs["thread_id"]
        self.assertTrue(created_id.startswith(f"{USER_ID}_coding_"))

    def test_upload_requires_ownership_and_non_running_thread(self):
        with patch("agent.api.coding_agent.get_task") as get_task:
            response = self.client.post(
                f"/regops/coding-agent/threads/{RISK_ID}/files?filename=main.py",
                content=b"print(1)",
            )
        self.assertEqual(response.status_code, 404)
        get_task.assert_not_called()

        with patch("agent.api.coding_agent.get_task", return_value={
            "thread_id": CODING_ID, "latest_run_status": "running",
        }):
            response = self.client.post(
                f"/regops/coding-agent/threads/{CODING_ID}/files?filename=main.py",
                content=b"print(1)",
            )
        self.assertEqual(response.status_code, 409)

    def test_existing_thread_can_prepare_replacement_sandbox(self):
        before = {"thread_id": CODING_ID, "latest_run_status": "failed", "sandbox_id": "expired"}
        after = {**before, "sandbox_id": "replacement"}
        with patch("agent.api.coding_agent.get_task", side_effect=[before, after]), patch(
            "agent.api.coding_agent.execution_backend", return_value="opensandbox",
        ), patch("agent.api.coding_agent.ensure_sandbox_for_thread", return_value=SimpleNamespace(id="replacement")), patch(
            "agent.api.coding_agent.consume_workspace_notice", return_value="已创建空沙箱",
        ):
            response = self.client.post(f"/regops/coding-agent/threads/{CODING_ID}/sandbox")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["sandbox_created"])
        self.assertEqual(response.json()["thread"]["id"], CODING_ID)
        self.assertEqual(response.json()["workspace_notice"], "已创建空沙箱")

    def test_upload_calls_sandbox_backend_with_owned_thread(self):
        thread = {"thread_id": CODING_ID, "latest_run_status": "idle", "sandbox_id": "sandbox-1"}
        uploaded = {
            "file_count": 1, "snapshot_saved": True, "message": "已导入", "workspace_notice": None,
        }
        with patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.upload_to_workspace", return_value=uploaded,
        ) as upload:
            response = self.client.post(
                f"/regops/coding-agent/threads/{CODING_ID}/files?filename=main.py",
                content=b"print(1)",
            )
        self.assertEqual(response.status_code, 200)
        upload.assert_called_once_with(CODING_ID, "main.py", b"print(1)")
        self.assertTrue(response.json()["snapshot_saved"])

    def test_options_report_unavailable_when_sandbox_mode_is_disabled(self):
        with patch("agent.api.coding_agent.execution_backend", side_effect=RuntimeError("仅支持 OpenSandbox")):
            response = self.client.get("/regops/coding-agent/options")
        self.assertEqual(response.status_code, 503)

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
        ), patch("agent.api.coding_agent.recall_snapshot", return_value=None):
            response = self.client.get(f"/regops/coding-agent/threads/{CODING_ID}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["author"] for item in response.json()["messages"]], ["user", "agent"])
        self.assertFalse(response.json()["snapshotReady"])

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

    def test_expired_export_returns_410_with_specific_reason(self):
        from agent.backends.open_sandbox import SandboxExpiredError

        thread = {"thread_id": CODING_ID, "latest_run_status": "completed", "sandbox_id": "expired"}
        with patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.export_project_zip", side_effect=SandboxExpiredError("沙箱已过期；代码无法恢复"),
        ):
            response = self.client.get(f"/regops/coding-agent/threads/{CODING_ID}/export")
        self.assertEqual(response.status_code, 410)
        self.assertIn("沙箱已过期", response.json()["detail"])

    def test_expired_existing_thread_keeps_same_conversation_without_eager_sandbox(self):
        thread = {"thread_id": CODING_ID, "latest_run_status": "completed", "sandbox_id": "expired"}
        with patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.require_agent_model_id", return_value="fake-model",
        ), patch("agent.api.coding_agent.execution_backend", return_value="opensandbox"), patch(
            "agent.api.coding_agent.save_export_snapshot",
        ), patch("agent.api.coding_agent.initialize_task_record") as initialize, patch(
            "agent.api.coding_agent.run_coding_task", return_value={"final_answer": "你好"},
        ) as run:
            response = self.client.post(
                f"/regops/coding-agent/threads/{CODING_ID}/stream-message",
                json={"content": "你好", "model_id": "fake-model"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("你好", response.text)
        initialize.assert_called_once()
        run.assert_called_once()

    def test_local_mode_rejected_before_writing_thread(self):
        thread = {"thread_id": CODING_ID}
        with patch("agent.api.coding_agent.require_agent_model_id", return_value="fake-model"), patch(
            "agent.api.coding_agent.execution_backend", side_effect=RuntimeError("AI Coding 仅支持 OpenSandbox"),
        ), patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.initialize_task_record",
        ) as initialize:
            response = self.client.post(
                f"/regops/coding-agent/threads/{CODING_ID}/stream-message",
                json={"content": "修改代码", "model_id": "fake-model"},
            )
        self.assertEqual(response.status_code, 503)
        initialize.assert_not_called()

    def test_completed_thread_without_sandbox_can_resume(self):
        thread = {"thread_id": CODING_ID, "latest_run_status": "completed", "sandbox_id": None}
        with patch("agent.api.coding_agent.require_agent_model_id", return_value="fake-model"), patch(
            "agent.api.coding_agent.execution_backend", return_value="opensandbox",
        ), patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.initialize_task_record",
        ) as initialize, patch("agent.api.coding_agent.run_coding_task", return_value={"final_answer": "已继续"}):
            response = self.client.post(
                f"/regops/coding-agent/threads/{CODING_ID}/stream-message",
                json={"content": "继续修改代码", "model_id": "fake-model"},
            )
        self.assertEqual(response.status_code, 200)
        initialize.assert_called_once()

    def test_sandbox_allows_default_workspace_without_project_selection(self):
        thread = {
            "thread_id": CODING_ID, "title": "默认工作区", "latest_run_status": "running",
            "created_at": "2026-10-09T00:00:00+00:00", "updated_at": "2026-10-09T00:01:00+00:00",
            "sandbox_project": None, "sandbox_id": None,
        }
        with patch("agent.api.coding_agent.require_agent_model_id", return_value="fake-model"), patch(
            "agent.api.coding_agent.execution_backend", return_value="opensandbox",
        ), patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.initialize_task_record",
        ), patch("agent.api.coding_agent.run_coding_task", return_value={"final_answer": "已完成"}) as run:
            response = self.client.post(
                f"/regops/coding-agent/threads/{CODING_ID}/stream-message",
                json={"content": "在默认工作目录创建示例", "model_id": "fake-model"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("已完成", response.text)
        self.assertEqual(run.call_args.kwargs["prompt"], "在默认工作目录创建示例")

    def test_completed_run_saves_export_snapshot(self):
        thread = {
            "thread_id": CODING_ID, "title": "项目", "latest_run_status": "completed",
            "sandbox_id": "sandbox-1", "created_at": "2026-10-09T00:00:00+00:00",
            "updated_at": "2026-10-09T00:01:00+00:00",
        }
        with patch("agent.api.coding_agent.require_agent_model_id", return_value="fake-model"), patch(
            "agent.api.coding_agent.execution_backend", return_value="opensandbox",
        ), patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.initialize_task_record",
        ), patch("agent.api.coding_agent.run_coding_task", return_value={"final_answer": "已完成"}), patch(
            "agent.api.coding_agent.save_export_snapshot",
        ) as save:
            response = self.client.post(
                f"/regops/coding-agent/threads/{CODING_ID}/stream-message",
                json={"content": "确认实施", "model_id": "fake-model"},
            )
        self.assertEqual(response.status_code, 200)
        save.assert_called_once_with(CODING_ID)

    def test_empty_workspace_run_does_not_show_export_warning(self):
        thread = {
            "thread_id": CODING_ID, "title": "聊天", "latest_run_status": "completed",
            "sandbox_id": "sandbox-1", "created_at": "2026-10-09T00:00:00+00:00",
            "updated_at": "2026-10-09T00:01:00+00:00",
        }
        with patch("agent.api.coding_agent.require_agent_model_id", return_value="fake-model"), patch(
            "agent.api.coding_agent.execution_backend", return_value="opensandbox",
        ), patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.initialize_task_record",
        ), patch("agent.api.coding_agent.run_coding_task", return_value={"final_answer": "你好"}), patch(
            "agent.api.coding_agent.save_export_snapshot", return_value=False,
        ):
            response = self.client.post(
                f"/regops/coding-agent/threads/{CODING_ID}/stream-message",
                json={"content": "👋", "model_id": "fake-model"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("event: export_warning", response.text)
        self.assertIn('"snapshotReady": false', response.text)

    def test_failed_run_does_not_retry_export_from_expired_sandbox(self):
        thread = {
            "thread_id": CODING_ID, "title": "旧会话", "latest_run_status": "failed", "sandbox_id": "expired",
            "created_at": "2026-10-09T00:00:00+00:00", "updated_at": "2026-10-09T00:01:00+00:00",
        }
        with patch("agent.api.coding_agent.require_agent_model_id", return_value="fake-model"), patch(
            "agent.api.coding_agent.execution_backend", return_value="opensandbox",
        ), patch("agent.api.coding_agent.get_task", return_value=thread), patch(
            "agent.api.coding_agent.initialize_task_record",
        ), patch("agent.api.coding_agent.run_coding_task", side_effect=RuntimeError("sandbox gone")), patch(
            "agent.api.coding_agent.save_export_snapshot",
        ) as save:
            response = self.client.post(
                "/regops/coding-agent/threads/stream-message",
                json={"content": "你好", "model_id": "fake-model"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: error", response.text)
        self.assertNotIn("event: export_warning", response.text)
        save.assert_not_called()

    def test_deleting_sandbox_thread_destroys_container_even_after_mode_change(self):
        with patch("agent.api.coding_agent.get_task", return_value={"sandbox_id": "sandbox-1"}), patch(
            "agent.api.coding_agent.destroy_sandbox_for_thread",
        ) as destroy, patch("agent.api.coding_agent.delete_task", return_value=True), patch(
            "agent.api.coding_agent.delete_saved_export",
        ) as delete_export:
            response = self.client.delete(f"/regops/coding-agent/threads/{CODING_ID}")
        self.assertEqual(response.status_code, 204)
        destroy.assert_called_once_with(CODING_ID)
        delete_export.assert_called_once_with(CODING_ID)

    def test_coding_stream_cannot_enter_financial_mode(self):
        thread = {
            "thread_id": CODING_ID, "title": "任务", "latest_run_status": "running",
            "created_at": "2026-10-09T00:00:00+00:00", "updated_at": "2026-10-09T00:01:00+00:00",
        }
        with patch("agent.api.coding_agent.require_agent_model_id", return_value="fake-model"), patch(
            "agent.api.coding_agent.execution_backend", return_value="opensandbox",
        ), patch(
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

        with patch("agent.coding.service.execution_backend", return_value="opensandbox"), patch(
            "agent.coding.service.run_agent_task", return_value={},
        ) as runtime:
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
