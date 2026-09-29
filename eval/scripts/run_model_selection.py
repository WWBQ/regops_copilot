#!/usr/bin/env python3
"""同一批金融小题对比 DeepSeek / Qwen，产出 docs/model_selection_w1.md 的原始测量。

用法（项目根）：
  python-ai/.venv/bin/python eval/scripts/run_model_selection.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python-ai"))

from app.models.llm import get_llm_client, list_available_models, resolve_model_id  # noqa: E402

OUT_PATH = ROOT / "eval" / "reports" / "model_selection_w1" / "raw.json"

# 清单示例题 + 若干合规/年报术语题；全部不依赖特定财报数字，避免和入库语料错配。
ITEMS: list[dict[str, str]] = [
    {
        "id": "ms-01",
        "question": "什么是「审慎监管」？用一句话说明其核心要义。",
        "look_for": "风险约束 / 稳健经营 / 资本与流动性要求",
    },
    {
        "id": "ms-02",
        "question": "商业银行资本充足率监管通常关注哪三个层次指标？请简要列出。",
        "look_for": "核心一级 / 一级 / 总资本充足率",
    },
    {
        "id": "ms-03",
        "question": "MLF（中期借贷便利）与 LPR（贷款市场报价利率）在政策传导中通常是什么关系？",
        "look_for": "MLF 影响银行负债成本，进而影响 LPR 报价",
    },
    {
        "id": "ms-04",
        "question": "反洗钱工作中，金融机构对客户通常要履行哪三项基本义务？",
        "look_for": "客户身份识别 / 大额和可疑交易报告 / 客户身份资料与交易记录保存",
    },
    {
        "id": "ms-05",
        "question": "不良贷款率升高通常意味着什么？对银行经营有何直接影响？",
        "look_for": "资产质量下降；需增提拨备、侵蚀利润与资本",
    },
    {
        "id": "ms-06",
        "question": "什么是「拨备覆盖率」？它衡量的是什么？",
        "look_for": "贷款损失准备 / 不良贷款余额",
    },
    {
        "id": "ms-07",
        "question": "巴塞尔协议III框架下，银行资本监管通常说的「三大支柱」是什么？",
        "look_for": "最低资本要求 / 监管审查 / 市场约束（信息披露）",
    },
    {
        "id": "ms-08",
        "question": "上市公司信息披露的「真实、准确、完整、及时」四性要求分别指什么？各用一句话。",
        "look_for": "四性均被分别解释，不串台、不漏项",
    },
]


async def run_one(model: str, question: str) -> dict:
    client = get_llm_client(model=model)
    result = await client.chat_with_usage(
        [{"role": "user", "content": question}],
        temperature=0.1,
    )
    return {
        "reply": result.content.strip(),
        "latency_ms": round(result.latency_ms, 1),
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
    }


async def main() -> int:
    available = list_available_models()
    missing = []
    for name in ("deepseek", "qwen"):
        try:
            resolve_model_id(name, available)
        except ValueError:
            missing.append(name)
    if missing:
        print(f"缺少模型 Key：{missing}；当前 available={available}", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for item in ITEMS:
        row: dict = {"id": item["id"], "question": item["question"], "look_for": item["look_for"]}
        for model in ("deepseek", "qwen"):
            print(f"{item['id']} {model} ...", flush=True)
            row[model] = await run_one(model, item["question"])
        rows.append(row)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": {
            "deepseek": "deepseek-chat",
            "qwen": "qwen-plus",
        },
        "temperature": 0.1,
        "items": rows,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
