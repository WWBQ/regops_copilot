# eval/dify

W8-4 Dify 与本仓库 `/chat` 对照的可提交说明。日常跑次在 `runs/`（gitignore），不要把平台 volume 或 PDF 提交进来。

| 文件 | 含义 |
|---|---|
| `examples/last_compare.md` | `--write-example` 覆盖写入的最近一次对照（可为「跳过」） |

```bash
./scripts/dify-up.sh
export DIFY_APP_KEY=app-...
python-ai/.venv/bin/python eval/run_w8_dify_compare.py --write-example
```

口径见 [`docs/dify-comparison.md`](../../docs/dify-comparison.md)。
