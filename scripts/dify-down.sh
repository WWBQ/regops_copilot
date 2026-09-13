#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCKER_DIR="$ROOT/dify/upstream/docker"

if [[ ! -f "$DOCKER_DIR/docker-compose.yaml" ]]; then
  echo "没有 dify/upstream/docker，无需停止。"
  exit 0
fi

if [[ "${1:-}" == "--wipe" ]]; then
  echo "将删除 Dify volumes。"
  docker compose -f "$DOCKER_DIR/docker-compose.yaml" --project-directory "$DOCKER_DIR" down -v
else
  docker compose -f "$DOCKER_DIR/docker-compose.yaml" --project-directory "$DOCKER_DIR" down
fi
echo "已停止。控制台不再占用 :1380。"
