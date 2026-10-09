# OpenSandbox：kind + Kubernetes 本地部署

这套部署只承载 AI Coding 的代码沙箱，不迁移 RegOps 的 PostgreSQL、Java、Python 或 Vue 服务。固定使用 OpenSandbox `release-1.1.0`，与 Agent 中的 `opensandbox==1.1.0` SDK 对应。kind 适合本机学习 Kubernetes 对象和调用链，不是生产级租户隔离环境。

```text
本机 AI Coding Agent
  └─ 127.0.0.1:8090 (kubectl port-forward)
      └─ OpenSandbox Lifecycle Server (API Key、ServiceAccount)
          ├─ BatchSandbox CRD → Controller → 每任务 Pod（sandbox + egress sidecar）
          └─ Ingress Gateway (签名路由) ← 127.0.0.1:8091 (port-forward)
```

## 1. 工具和集群

需要 Docker Desktop、`kubectl`、kind 和 Helm 3。安装或下载官方 release 后检查版本：

```sh
kind version
helm version --short
kubectl version --client
```

本机首次部署把经过 SHA256 校验的 kind v0.33.0、Helm v3.22.0 和独立 kubeconfig 放在 Git 忽略的 `deploy/opensandbox/.local/`。在当前仓库的终端可先执行：

```sh
export REGOPS_ROOT=/Users/chengfeng/Desktop/AI/regops_copilot
export PATH="$REGOPS_ROOT/deploy/opensandbox/.local:$PATH"
export KUBECONFIG="$REGOPS_ROOT/deploy/opensandbox/.local/kubeconfig"
```

如果以后重建集群，需用 `kind export kubeconfig --name regops-sandbox --kubeconfig "$KUBECONFIG"` 更新它；不要提交 kubeconfig（含客户端证书密钥）。

创建专用集群，避免覆盖仓库已有的全栈 kind 配置：

```sh
kind create cluster --name regops-sandbox --wait 120s
kubectl config use-context kind-regops-sandbox
kubectl create namespace opensandbox-system
kubectl create namespace opensandbox
```

为避免误操作其他集群，下面的命令都建议额外指定 `--context kind-regops-sandbox`；也可以像本机首次部署那样使用独立 `KUBECONFIG`。`opensandbox-system` 放控制平面，`opensandbox` 放临时工作负载。

## 2. 准备 Helm chart 和 Secret

从 OpenSandbox 官方仓库固定版本取 chart，不用浮动 `main`：

```sh
git clone --depth 1 --branch release-1.1.0 https://github.com/opensandbox-group/OpenSandbox.git /tmp/OpenSandbox-release-1.1.0
cd /tmp/OpenSandbox-release-1.1.0
```

在 `opensandbox-system` 中创建两个 Secret：一个是生命周期 API Key，另一个是网关签名密钥。不要把值放在 Helm values 或 Git 中。可沿用 RegOps 根目录 `.env` 的 `AI_CODING_SANDBOX_API_KEY`；先检查它不为空，并在当前 shell 中执行：

```sh
read -s 'sandbox_key?OpenSandbox API Key: '
echo
kubectl --context kind-regops-sandbox -n opensandbox-system create secret generic opensandbox-api-key --from-literal=api-key="$sandbox_key"
unset sandbox_key

signing_key=$(openssl rand -base64 32)
kubectl --context kind-regops-sandbox -n opensandbox-system create secret generic opensandbox-gateway-signing --from-literal=keys="a=$signing_key" --from-literal=active-key=a
unset signing_key
```

`read -s` 命令按 zsh 写；若使用 bash，改为 `read -s -p 'OpenSandbox API Key: ' sandbox_key`。首次部署已把本机 `.env` 中的 Key 导入集群，不需要再次生成不同 Key。

## 3. 依次部署四层

以下路径中的 `REGOPS_ROOT` 指本仓库绝对路径。不要启用 FastSandbox：本地 kind 不提供它需要的 KVM 节点。

```sh
export REGOPS_ROOT=/Users/chengfeng/Desktop/AI/regops_copilot
helm --kube-context kind-regops-sandbox install opensandbox-base manifests/charts/base -n opensandbox-system \
  --set fastSandbox.crds.install=false \
  --set fastSandbox.namespaces.create=false \
  --set fastSandbox.rbac.create=false

helm --kube-context kind-regops-sandbox install opensandbox-controller manifests/charts/controller -n opensandbox-system
helm --kube-context kind-regops-sandbox install opensandbox-gateway manifests/charts/ingress-gateway -n opensandbox-system \
  -f "$REGOPS_ROOT/deploy/opensandbox/kind-gateway-values.yaml"
helm --kube-context kind-regops-sandbox install opensandbox-server manifests/charts/server -n opensandbox-system \
  -f "$REGOPS_ROOT/deploy/opensandbox/kind-server-values.yaml"
```

四层分别负责：CRD/RBAC 定义沙箱资源和权限；Controller 把 BatchSandbox 调谐为 Pod；Gateway 代理到具体沙箱并校验路由签名；Server 提供创建、续期、销毁等 API。Server 的 API Key 和网关签名密钥均来自 Kubernetes Secret。

```sh
kubectl --context kind-regops-sandbox -n opensandbox-system get pods
kubectl --context kind-regops-sandbox get crd batchsandboxes.sandbox.opensandbox.io
kubectl --context kind-regops-sandbox -n opensandbox-system rollout status deployment/opensandbox-server
```

## 4. 本机访问和验收

分别在两个终端保持以下进程运行。只绑定本机回环地址，停止端口转发后 Agent 会报连接错误，不会回退到本机执行：

```sh
kubectl --context kind-regops-sandbox -n opensandbox-system port-forward --address 127.0.0.1 service/opensandbox-server 8090:80
```

```sh
kubectl --context kind-regops-sandbox -n opensandbox-system port-forward --address 127.0.0.1 service/opensandbox-ingress-gateway 8091:80
```

验证公开健康检查和无 Key 拒绝访问：

```sh
curl -i http://127.0.0.1:8090/health
curl -i http://127.0.0.1:8090/v1/sandboxes
```

前者应为 `200`，后者应为 `401`。再运行独立 smoke：

```sh
cd "$REGOPS_ROOT/financial-risk-audit-assistant"
PYTHONPATH=. .venv/bin/python ../deploy/opensandbox/smoke.py
```

Smoke 会创建一次性受限 Pod，检查命令执行、文件读写、DNS 和公网 IP 直连均被阻断，然后销毁 Pod。首次使用需要拉取约 2.6 GB 的代码解释器镜像，可能耗时几分钟；不要仅凭 Helm `STATUS=deployed` 就认为沙箱可用。

验收通过后，本机 Agent 使用根目录 `.env`：

```dotenv
AI_CODING_EXECUTION_BACKEND=opensandbox
AI_CODING_SANDBOX_DOMAIN=127.0.0.1:8090
AI_CODING_SANDBOX_PROTOCOL=http
AI_CODING_SANDBOX_API_KEY=<与 Kubernetes Secret 相同的 Key>
```

重新启动本机 `risk-agent` 才能确保新配置生效。这个端口转发仅适用于运行在宿主机的 Agent；Docker Compose 容器内的 `localhost` 指容器自身，不能直接复用，必须另外设计仅容器可达的安全入口。

## 5. 常用排查

```sh
kubectl --context kind-regops-sandbox -n opensandbox get pods,batchsandboxes
kubectl --context kind-regops-sandbox -n opensandbox get events --sort-by=.lastTimestamp
kubectl --context kind-regops-sandbox -n opensandbox-system logs deployment/opensandbox-server --tail=100
kubectl --context kind-regops-sandbox -n opensandbox-system logs deployment/opensandbox-controller-manager --tail=100
```

已知告警：`release-1.1.0` 的可选 FastSandbox 快照监视器会请求 `sandboxesnapshots.sandbox.fast.io`，而对应发布的 CRD 复数名是 `sandboxsnapshots`。因此 Server 日志可能每隔一段时间出现 informer `404`；本部署不启用 FastSandbox 快照路径，实际的 BatchSandbox 创建、文件与命令接口仍以 smoke 结果为准。单纯安装 FastSandbox CRD 不能修复此命名差异。升级 OpenSandbox 时应重新验证这一点。

不要用 `kubectl delete namespace` 或 `kind delete cluster` 清理，除非确认不再需要这个本地集群；这会同时删除所有沙箱和它们的临时文件。

官方资料：[OpenSandbox Kubernetes 部署](https://github.com/opensandbox-group/OpenSandbox/blob/release-1.1.0/docs/deployment/index.md)、[kind Quick Start](https://kind.sigs.k8s.io/docs/user/quick-start/)。
