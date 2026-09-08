#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CLUSTER="${KIND_CLUSTER:-regops}"

if ! command -v kind >/dev/null 2>&1; then
  echo "需要 kind：https://kind.sigs.k8s.io/docs/user/quick-start/" >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "需要 kubectl" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "需要 docker" >&2
  exit 1
fi

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  kind create cluster --name "$CLUSTER" --config k8s/kind-config.yaml
fi

echo "构建本地镜像（python-ai 首次含 torch/docling，会较慢）…"
docker build -t regops/python-ai:local -f python-ai/Dockerfile .
docker build -t regops/java-service:local ./java-service
docker build -t regops/web:local ./web

kind load docker-image regops/python-ai:local --name "$CLUSTER"
kind load docker-image regops/java-service:local --name "$CLUSTER"
kind load docker-image regops/web:local --name "$CLUSTER"

kubectl apply -k k8s/

echo
echo "已 apply。前端 http://localhost:8088  Java http://localhost:8080/api/health"
echo "NodePort 不通时：kubectl -n regops port-forward svc/web 8088:80"
echo "无 AI 降级演示：kubectl -n regops scale deploy/python-ai --replicas=0"
echo "   此时 GET /api/health 仍 200，pythonAi.status=down；复核/审计可继续。"
