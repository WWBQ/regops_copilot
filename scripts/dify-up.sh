#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPSTREAM="$ROOT/dify/upstream"
DOCKER_DIR="$UPSTREAM/docker"
OVERLAY="$ROOT/dify/.env.overlay"

if ! command -v docker >/dev/null 2>&1; then
  echo "需要 docker。" >&2
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then
  echo "需要 git（浅克隆官方 docker/）。" >&2
  exit 1
fi

if [[ ! -f "$DOCKER_DIR/docker-compose.yaml" ]]; then
  echo "浅克隆 langgenius/dify → $UPSTREAM …"
  rm -rf "$UPSTREAM"
  git clone --depth 1 --filter=blob:none --sparse https://github.com/langgenius/dify.git "$UPSTREAM"
  git -C "$UPSTREAM" sparse-checkout set docker
fi

if [[ ! -f "$DOCKER_DIR/.env" ]]; then
  cp "$DOCKER_DIR/.env.example" "$DOCKER_DIR/.env"
fi

if [[ -f "$OVERLAY" ]]; then
  if ! grep -q "EXPOSE_NGINX_PORT=1380" "$DOCKER_DIR/.env"; then
    {
      echo ""
      echo "# --- regops overlay (ports avoid 5173/8000/8080/5432) ---"
      cat "$OVERLAY"
    } >> "$DOCKER_DIR/.env"
  fi
fi

echo "启动 Dify（控制台 http://localhost:1380 ）…"
docker compose -f "$DOCKER_DIR/docker-compose.yaml" --project-directory "$DOCKER_DIR" up -d

echo
echo "下一步："
echo "  1. 打开 http://localhost:1380 注册管理员、配 DeepSeek/Qwen"
echo "  2. 知识库导入 data/raw/*_2024_annual.pdf"
echo "  3. 建 RAG Chatbot，复制 App API Key"
echo "  4. export DIFY_APP_KEY=app-... && python-ai/.venv/bin/python eval/run_w8_dify_compare.py"
echo "停：./scripts/dify-down.sh"
