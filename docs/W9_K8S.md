# W9-5 最小 Kubernetes 与信创路径

> 日常一键仍是 Compose（[`W9_COMPOSE.md`](./W9_COMPOSE.md)）。K8s 给要调度、滚动、探针和命名空间隔离的时候用。清单在 `k8s/`，可在 **kind 或 minikube** 上 apply。

## 有什么

| 对象 | 作用 |
|---|---|
| Namespace `regops` | 与本地 Compose 项目名分开 |
| ConfigMap `regops-config` | 非密钥：库名、Java→Python URL、对象存储路径 |
| Secret `regops-secrets` | JWT、服务 token、库密码、LLM Key。仓库里是 **演示值**，与 `.env.example` 对齐 |
| ConfigMap `postgres-init` | `k8s/init/*.sql`（与 Compose 挂载的 `docs/sql` 同内容、同顺序） |
| Deployment + Service | `postgres`、`python-ai`、`java-service`、`web` |
| PVC | `postgres-data` 1Gi、`python-data` 5Gi |
| Probe | db `pg_isready`；python `GET /health`；java `GET /api/health`；web `GET /healthz` |

Java **不** 等 python-ai Ready。`GET /api/health` 在 Python 挂掉时仍返回 200，`pythonAi.status=down`。这是 W9-6 降级的集群侧依据：

```bash
kubectl -n regops scale deploy/python-ai --replicas=0
```

前端问答会提示不可用，合规复核和审计继续走 Java + Postgres。

没有 Ingress。kind 用 NodePort：`web 30088→80`、`java-service 30080→8080`。`k8s/kind-config.yaml` 把它们映射到本机 **8088 / 8080**。

## 本地跑通（kind）

```bash
# 1. 装 kind + kubectl + docker
# 2. 构建并 load 镜像后 apply
./scripts/kind-up.sh
```

分步等价于：

```bash
kind create cluster --name regops --config k8s/kind-config.yaml
docker build -t regops/python-ai:local -f python-ai/Dockerfile .
docker build -t regops/java-service:local ./java-service
docker build -t regops/web:local ./web
kind load docker-image regops/python-ai:local --name regops
kind load docker-image regops/java-service:local --name regops
kind load docker-image regops/web:local --name regops
kubectl apply -k k8s/
kubectl -n regops get pods,svc
```

业务镜像 `imagePullPolicy: Never`，必须先 load。`pgvector/pgvector:pg16` 可从仓库拉。

python-ai 镜像含 torch / docling，**首次构建很慢**，内存建议 ≥4Gi。小 kind 节点若 OOM，把副本打到 0 仍能演示 Java 复核（W9-6）。

minikube：

```bash
minikube start
# 同一套 docker build 后
minikube image load regops/python-ai:local
minikube image load regops/java-service:local
minikube image load regops/web:local
kubectl apply -k k8s/
minikube service web -n regops
```

改表结构先改 `docs/sql/`，再复制到 `k8s/init/`（文件名 `01_`–`08_` 与 Compose 挂载顺序一致）。Kustomize 不能引用 overlay 目录外的文件，所以 SQL 在清单里留一份。

只检查清单、不启集群：

```bash
kubectl kustomize k8s/ >/dev/null
kubectl apply --dry-run=client --validate=false -k k8s/
```

## 密钥

`k8s/secret.yaml` 是演示 Secret，**可以 apply，不能当生产**。覆盖步骤：

1. 复制为 `k8s/secret.local.yaml`（已 gitignore）
2. 填真实 `DEEPSEEK_API_KEY` / `REGOPS_JWT_SECRET`
3. `kubectl -n regops apply -f k8s/secret.local.yaml`

生产应改用 sealed-secret、外部密钥或云厂商 Secret Store，不要把 Key 打进镜像层。

## 金融私有化与信创（有依据，不假装过认证）

本仓库 **不依赖 OpenAI**。默认模型已是 **DeepSeek / Qwen**，Key 走环境变量。私有化时把 `REGOPS_PYTHON_AI_BASE_URL` 指到内网网关即可，清单不用改业务代码。

数据库走 **PostgreSQL 协议 + pgvector**。信创替换路径是 **兼容 Postgres 的国产发行**（PolarDB-PostgreSQL、Vastbase、GaussDB for PostgreSQL 等），向量扩展需对方提供 pgvector 或等价算子。

**不是**「换成达梦就完事」：达梦不是 Postgres 协议，本仓库的 HNSW / `vector(1024)` 对不上。若必须达梦，RAG 要拆出独立向量库，问数事实表另迁，工作量和风险都要单独评估。

JDK：当前镜像是 Eclipse Temurin 21。信创主机可换成 **Alibaba Dragonwell 21** 或 **毕昇 JDK 21**，作为 Temurin 的 drop-in（需回归 `mvn test`）。容器化后宿主机 libc（麒麟 / 统信）锁得住的是节点 OS，不是把业务绑死在某套国产中间件认证上。

面试时说清楚：**Compose 可复现样板；K8s 是上规模路径；信创先锁模型与 PG 协议，再谈发行版采购。** 不要说「已经过某家等保/信创测评」——仓库没有那些证书。

课程口试对应 **q46**。
