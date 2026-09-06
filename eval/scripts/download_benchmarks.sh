#!/usr/bin/env bash
# 打印公开金融基准的官方入口与许可。默认不下数据。
# 用法：
#   ./eval/scripts/download_benchmarks.sh cflue
#   ./eval/scripts/download_cflue.sh
#
# 仓库规则：不 commit 原数据。若自行下载，放到 eval/.cache/benchmarks/<name>/（已 gitignore）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CACHE="$ROOT/eval/.cache/benchmarks"

print_block() {
  local name="$1"
  echo "=== $name ==="
  shift
  printf '%s\n' "$@"
  echo
  echo "本地缓存目录（不要提交）：$CACHE/$name"
  echo "选型卡：docs/benchmarks/"
}

case "${1:-}" in
  cflue)
    print_block cflue \
      "代码 MIT · 数据集 CC BY-NC-SA 4.0（禁止商用、ShareAlike）" \
      "GitHub:    https://github.com/aliyun/cflue" \
      "ModelScope:https://www.modelscope.cn/datasets/tongyi_dianjin/CFLUE" \
      "HuggingFace:https://huggingface.co/datasets/DianJin/CFLUE" \
      "论文:      https://aclanthology.org/2024.findings-acl.337/"
    ;;
  fineval)
    print_block fineval \
      "评测代码 Apache-2.0 · 数据集经 HF 分发 · test 标签不公开" \
      "GitHub:    https://github.com/SUFE-AIFLM-Lab/FinEval" \
      "文档:      https://fineval.readthedocs.io/" \
      "HuggingFace:https://huggingface.co/datasets/SUFE-AIFLM-Lab/FinEval" \
      "zip:       https://huggingface.co/datasets/SUFE-AIFLM-Lab/FinEval/resolve/main/FinEval.zip" \
      "论文:      https://arxiv.org/abs/2308.09975"
    ;;
  finqa)
    print_block finqa \
      "FinQA 代码 MIT · 数据项目页 CC BY 4.0" \
      "TAT-QA 代码 MIT · 数据 CC BY 4.0" \
      "FinQA:     https://github.com/czyssrs/FinQA" \
      "           https://finqasite.github.io/" \
      "           https://huggingface.co/datasets/ibm-research/finqa" \
      "TAT-QA:    https://github.com/NExTplusplus/TAT-QA" \
      "           https://huggingface.co/datasets/next-tat/TAT-QA" \
      "选型卡:    docs/benchmarks/FinQA_TATQA.md"
    ;;
  financebench)
    print_block financebench \
      "开源 150 条 · CC BY-NC-4.0（非商业）· 全量 10231 条不开放" \
      "GitHub:    https://github.com/patronus-ai/financebench" \
      "HuggingFace:https://huggingface.co/datasets/PatronusAI/financebench" \
      "PDF 目录:  https://github.com/patronus-ai/financebench/tree/main/pdfs" \
      "全量咨询:  contact@patronus.ai" \
      "论文:      https://arxiv.org/abs/2311.11944"
    ;;
  finmteb)
    print_block finmteb \
      "64 子集各自保留原许可，使用前读该集 HF license 字段" \
      "GitHub:    https://github.com/yixuantt/FinMTEB" \
      "Org:       https://huggingface.co/FinanceMTEB" \
      "榜单:      https://huggingface.co/spaces/FinanceMTEB/FinanceMTEB_Leaderboard" \
      "论文:      https://arxiv.org/abs/2502.10990" \
      "本项目不下载 64 集；W3 检索门禁用 eval/golden/rag_retrieval_100.json"
    ;;
  *)
    echo "用法: $0 {cflue|fineval|finqa|financebench|finmteb}" >&2
    exit 1
    ;;
esac
