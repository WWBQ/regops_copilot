#!/bin/sh
# 把 AI Coding 沙箱镜像放进 kind 节点。kind 不使用宿主机的 Docker 镜像加速，
# 节点里没有这些镜像时，沙箱 Pod 会在 60 秒内一直 Pending。
set -eu

cluster=regops-sandbox
node="${cluster}-control-plane"
interpreter="opensandbox/code-interpreter:v1.1.0"
execd="sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/execd:release-1.1.0"
egress="sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/egress:release-1.1.0"

docker start "$node" >/dev/null

if ! docker image inspect "$interpreter" >/dev/null 2>&1; then
  docker pull "docker.1ms.run/${interpreter}"
  docker tag "docker.1ms.run/${interpreter}" "$interpreter"
fi

echo "import ${interpreter}"
docker save "$interpreter" | docker exec -i "$node" ctr -n k8s.io images import -

echo "pull ${execd}"
docker exec "$node" ctr -n k8s.io images pull "$execd"

echo "pull ${egress}"
docker exec "$node" ctr -n k8s.io images pull "$egress"

docker exec "$node" ctr -n k8s.io images ls | grep -E 'code-interpreter|opensandbox/execd|opensandbox/egress'
