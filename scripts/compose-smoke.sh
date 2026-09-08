#!/usr/bin/env bash
# Compose 交付冒烟：四个服务健康 + 经 Java 的五条链路。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

wait_url() {
  local url="$1"
  local n=0
  until curl -fsS "$url" >/dev/null 2>&1; do
    n=$((n + 1))
    if [[ "$n" -gt 60 ]]; then
      echo "timeout waiting for $url" >&2
      exit 1
    fi
    sleep 2
  done
  echo "ok $url"
}

wait_url "http://localhost:8000/health"
wait_url "http://localhost:8080/api/health"
wait_url "http://localhost:8088/healthz"

python-ai/.venv/bin/python eval/run_w9_e2e.py --base http://localhost:8080
python-ai/.venv/bin/python eval/run_w9_redteam.py --fail-on-regression
