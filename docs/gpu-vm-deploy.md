# 云 GPU 虚拟机部署记录

2026-10-11 把 RegOps Copilot 部署到一台租用的 RTX 3090 虚拟机。本文只记录这次实际走通的过程，不是从零开始的通用安装手册。

前半是按顺序执行、并且最后生效的命令。后半是中间踩过的坑。两边分开写，避免把失败尝试和成功命令混在一起。

站点：http://117.50.46.222/

演示账号：

| 用户 | 密码 | 部门 | 能看的公司 |
| --- | --- | --- | --- |
| analyst | analyst123 | research | 002594、601633 |
| rm | rm123 | rm | 000333、000651 |
| admin | admin123 | compliance | 全部七家 |

| 项 | 值 |
| --- | --- |
| 实例 | regops，uhost-1wc4ao9u5div |
| 系统 | Ubuntu 22.04，用户 `ubuntu` |
| 配置 | RTX 3090 24GB，16 核，64GB 内存，100GB 磁盘 |
| 公网 | 117.50.46.222 |
| 内网 | 10.60.252.39 |
| Docker 网关 | 172.18.0.1 |
| 连接 | `ssh ubuntu@117.50.46.222` |

选这台是因为 4 核 16G 同时跑 BGE 向量、bge-reranker 精排和 PDF 解析太紧。vLLM 只能替换对话大模型，替换不了 BGE、精排和 MinerU。

命令分两处执行：

- Mac 终端提示符是 `chengfeng@…`。
- 服务器终端提示符是 `ubuntu@10-60-252-39`。

云防火墙只放行 22、80、443。不要开放 5432、8000、8080、2024、8090、8091。

## 部署命令

下面是最后留在机器上的做法。apt 源、pip 源、torch 和 torchvision 的版本、网页端口和 GPU 都已经写进仓库。云上启动时加上 `compose.gpu.yaml`，并在 `.env` 里设置 `WEB_PORT=80`。

### 1. 显卡驱动

在服务器上：

```bash
sudo apt-get update
sudo apt-get install -y nvidia-driver-550
sudo reboot
```

重新连上之后：

```bash
nvidia-smi
```

当时的结果是 RTX 3090，驱动 580.178.04，显存 24576 MiB。

### 2. Docker 和 GPU 容器

在服务器上：

```bash
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker ubuntu
```

退出 SSH 再登录。然后安装 NVIDIA 容器运行时：

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

保留已有的 nvidia runtime，只加上镜像加速：

```bash
sudo python3 - <<'PY'
import json
path = "/etc/docker/daemon.json"
try:
    data = json.load(open(path))
except FileNotFoundError:
    data = {}
data["registry-mirrors"] = [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run",
]
json.dump(data, open(path, "w"), indent=2)
print(json.dumps(data, indent=2))
PY
sudo systemctl restart docker
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

### 3. 代码和 .env

在服务器上克隆私有仓库：

```bash
git clone git@github.com:WWBQ/regops_copilot.git ~/regops_copilot
```

在 Mac 上把环境文件拷过去：

```bash
scp /Users/chengfeng/Desktop/AI/regops_copilot/.env ubuntu@117.50.46.222:~/regops_copilot/.env
```

在服务器上改 `.env`。密钥从 `~/sandbox-api-key.txt` 读入，命令本身不打印它：

```bash
cd ~/regops_copilot
sandbox_key=$(tr -d '[:space:]' < "$HOME/sandbox-api-key.txt")
python3 - "$sandbox_key" <<'PY'
import sys
from pathlib import Path
key = sys.argv[1]
updates = {
    "EMBEDDING_LOCAL_FILES_ONLY": "false",
    "HF_ENDPOINT": "https://hf-mirror.com",
    "HF_HUB_DISABLE_XET": "1",
    "STARTUP_WARMUP_ENABLED": "false",
    "AI_CODING_EXECUTION_BACKEND": "opensandbox",
    "AI_CODING_SANDBOX_DOMAIN": "172.18.0.1:8090",
    "AI_CODING_SANDBOX_PROTOCOL": "http",
    "WEB_PORT": "80",
    "AI_CODING_SANDBOX_API_KEY": key,
}
path = Path(".env")
lines = path.read_text().splitlines()
seen = set()
out = []
for line in lines:
    name = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else None
    if name in updates:
        out.append(f"{name}={updates[name]}")
        seen.add(name)
    else:
        out.append(line)
for name, value in updates.items():
    if name not in seen:
        out.append(f"{name}={value}")
path.write_text("\n".join(out) + "\n")
print("updated", ", ".join(name for name in updates if name != "AI_CODING_SANDBOX_API_KEY"))
PY
unset sandbox_key
```

上面的命令会写入 `WEB_PORT=80`。apt 源、pip 源和 `torch==2.6.0+cu124` / `torchvision==0.21.0+cu124` 在 `python-ai/Dockerfile`、`java-service/Dockerfile` 里。GPU 在 `compose.gpu.yaml`，没有显卡的机器不要加这个文件。

### 4. 启动 Compose

在服务器上：

```bash
cd ~/regops_copilot
docker compose -f compose.yaml -f compose.gpu.yaml build
docker compose -f compose.yaml -f compose.gpu.yaml up -d
```

起来之后的容器：

| 容器 | 作用 |
| --- | --- |
| regops-db | Postgres + pgvector |
| regops-redis | Redis，只绑 127.0.0.1 |
| regops-rabbitmq | RabbitMQ，只绑 127.0.0.1 |
| regops-searxng | 搜索 |
| regops-python | RAG / 问数 / 入库，8000 |
| regops-ingest-worker | PDF 解析 |
| regops-risk-agent | 风险审计和 AI Coding，2024 |
| regops-java | BFF，8080 |
| regops-web | nginx，宿主机 80 |

浏览器打开 http://117.50.46.222/ 。

### 5. 年报原件

PDF 字节不在数据库里。Mac 上的文件在 `data/objects`，容器目录是 `/app/data/objects`。

在 Mac 上：

```bash
rsync -a data/objects/ ubuntu@117.50.46.222:~/regops-objects/
```

在服务器上：

```bash
docker cp ~/regops-objects/. regops-python:/app/data/objects/
```

导入后的库是 `pdf_document` 12 行、`doc_chunks` 12441 行。

### 6. torchvision

在服务器上，于 `regops-python` 已经启动之后安装，然后只重启这个容器：

```bash
docker exec -it regops-python pip install --no-deps \
  https://download.pytorch.org/whl/cu124/torchvision-0.21.0%2Bcu124-cp312-cp312-linux_x86_64.whl
docker restart regops-python
docker exec regops-python python -c "import torch, torchvision; print(torch.__version__, torchvision.__version__)"
```

期望输出是 `2.6.0+cu124` 和 `0.21.0+cu124`。

如果为了让新的环境变量生效而 recreate 过 `python-ai`，上面的安装会被清掉，需要再执行一次，并且仍然只 `docker restart`。

### 7. 预加载模型

在服务器上。这条命令不受网页 180 秒超时限制：

```bash
docker exec -it regops-python python -c "
from sentence_transformers import SentenceTransformer, CrossEncoder
SentenceTransformer('BAAI/bge-m3', device='cuda')
CrossEncoder('BAAI/bge-reranker-v2-m3', device='cuda')
print('ready')
"
```

走通的标志：用 analyst 问「比亚迪2024年发布了哪些车型」，证据面板出现年报第 16 页的原文。

### 8. PDF worker 的响应类型

在服务器上给正在运行的网页容器加上 `.mjs` 类型并重新加载：

```bash
docker exec regops-web nginx -t
docker exec regops-web nginx -s reload
curl -sI http://127.0.0.1/assets/pdf.worker.min-CjEcRF4W.mjs | head
```

响应应是 `HTTP/1.1 200` 和 `Content-Type: application/javascript`。仓库里的 `web/nginx.conf` 已经有同样的 location。当时生效的是容器里当场改的配置。

浏览器用无痕窗口打开 http://117.50.46.222/index.html 。无痕窗口里可以打开第 16 页，总页数 290。

页码闪烁的修复在 `DocumentPdfFrame.vue`。要出现在线上，在 Mac 上拷文件，再在服务器上只重建网页：

```bash
scp web/src/components/documents/DocumentPdfFrame.vue \
  ubuntu@117.50.46.222:~/regops_copilot/web/src/components/documents/DocumentPdfFrame.vue
scp web/nginx.conf ubuntu@117.50.46.222:~/regops_copilot/web/nginx.conf
```

```bash
cd ~/regops_copilot
docker compose build web
docker compose up -d web
```

只重建 `web`。

### 9. OpenSandbox 控制平面

kind v0.33.0、kubectl v1.32.2、helm v3.22.0 放在服务器的 `/usr/local/bin`。集群名 `regops-sandbox`，命名空间 `opensandbox-system` 和 `opensandbox`，Helm chart 为 `release-1.1.0`。网关写成 `172.18.0.1:8091`，让 Compose 网络里的 risk-agent 能访问宿主机。

在服务器上把 API 转到 Docker 网关：

```bash
nohup kubectl -n opensandbox-system port-forward --address 0.0.0.0 service/opensandbox-server 8090:80 > /tmp/sb-server.log 2>&1 &
nohup kubectl -n opensandbox-system port-forward --address 0.0.0.0 service/opensandbox-ingress-gateway 8091:80 > /tmp/sb-gateway.log 2>&1 &
curl -s http://127.0.0.1:8090/health
```

`/health` 返回 200 表示控制平面可访问。kind 节点看不到宿主机已经拉好的镜像，沙箱会一直 Pending。在服务器上把三张镜像放进节点：

```bash
cd ~/regops_copilot
sh deploy/opensandbox/load-kind-images.sh
```

### 10. 关机后再开机

在云控制台开机，等一会儿再连。关机只停计费，磁盘还在，不要删实例。

在服务器上：

```bash
ssh ubuntu@117.50.46.222
nvidia-smi
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

`regops-web`、`regops-python`、`regops-java`、`regops-db` 都是 Up 之后，打开 http://117.50.46.222/ 。第一次提问会把模型载入显卡，模型文件还在数据卷里。

容器如果是 Exited：

```bash
cd ~/regops_copilot
docker compose -f compose.yaml -f compose.gpu.yaml up -d
```

不要加 `--build`，也不要 `--force-recreate`。

问答和年报预览不依赖 OpenSandbox。要用 AI Coding 时再补：

```bash
docker start regops-sandbox-control-plane
kubectl get nodes
nohup kubectl -n opensandbox-system port-forward --address 0.0.0.0 service/opensandbox-server 8090:80 > /tmp/sb-server.log 2>&1 &
nohup kubectl -n opensandbox-system port-forward --address 0.0.0.0 service/opensandbox-ingress-gateway 8091:80 > /tmp/sb-gateway.log 2>&1 &
curl -s http://127.0.0.1:8090/health
```

公网 IP 如果变了，项目配置不用改。网页用的是相对路径 `/api`，容器之间用的是 Docker 内部名字。用新 IP 做 SSH，并在新实例的防火墙上仍然只放行 22、80、443。`172.18.0.1` 是 Docker 网关，不是云平台的公网 IP。

## 踩过的坑

### 命令贴错终端

`sudo reboot` 有一次贴进了 Mac 终端。`scp .env` 有一次在服务器上执行，路径 `/Users/chengfeng/...` 在那边不存在。多行脚本贴进 GitHub 用户名提示时，后面的行会被吃掉，先 Ctrl+C 再重来。

### 驱动安装后的重启提示

apt 弹出 “Daemons using outdated libraries” 时选 Ok。SSH 断开是重启的正常现象。

### Docker 安装源和镜像加速

阿里云 docker-ce 源在这台机器上没有可安装的候选包，`docker.list` 没有真正生效，apt 只看得到 `mirrors.ucloud.cn`。最后用的是 Ubuntu 自带的 `docker.io` 和 `docker-compose-v2`（Compose v2.40.3）。

`nvidia-container-toolkit.list` 的 `tee` 如果被终端折行，软件源会写坏。

第一次 `docker run nvidia/cuda` 直连 `registry-1.docker.io` 超时。镜像加速写成 `docker.m.daocloud.io` 和 `docker.1ms.run`。写 `daemon.json` 时要保留 `nvidia-ctk` 已经写好的 nvidia runtime，不能整文件覆盖。

### 私有仓库和 .env

匿名 `git clone` 返回 404，并停在 GitHub 用户名提示。需要能访问 `WWBQ/regops_copilot` 的账号。

`.env` 不要提交。Mac 上原来的 `AI_CODING_EXECUTION_BACKEND=opensandbox` 指向 Mac 的 kind。第一次部署脚本把它改成了 `local`，当前代码只接受 `opensandbox`，会报「不会回退到本机执行」。

`EMBEDDING_LOCAL_FILES_ONLY` 默认是 true，服务器上没有现成的模型文件，必须改成 false。`STARTUP_WARMUP_ENABLED=true` 会在 `/health` 之前下载模型，健康检查起不来，服务器上关掉它。

Compose 会覆盖容器里的 `DATABASE_URL`。宿主机 `.env` 里的本机数据库口令不会直接给容器用。

### 构建源和端口

仓库里的网页端口当时是 `8088:80`。这台机器的防火墙只放行 80。后来写进仓库的做法是：`compose.yaml` 使用 `WEB_PORT`，默认仍是 8088，云上的 `.env` 设为 80；GPU 放在 `compose.gpu.yaml`，避免没有显卡的机器启动失败。

第一次 `docker compose build` 走 `deb.debian.org`，大约 92 分钟还停在 apt，停掉后换成阿里云 apt 和清华 pip 才构建成功。这两处源，以及 `torch==2.6.0+cu124` 和 `torchvision==0.21.0+cu124` 的直链安装，现在在 `python-ai/Dockerfile` 和 `java-service/Dockerfile` 里。

db 和 java 在容器里发布了 5432 和 8080。防火墙不要放行。

### 空库和年报原件

刚起来的库只有表结构、Java 种子用户和问数别名。年报 PDF 的键是 `reports/{doc_id}/{hash}.pdf`，桶名 `regops-docs`，卷名 `regops_copilot_python_data`。对象还没拷进容器时，预览接口是 404，页面文案是「年报源文件不存在或已移除」。

### torchvision 和 Hugging Face

`python-ai` 镜像先装 `requirements.txt`，再强制重装 cu124 的 torch。sentence-transformers 带进来的 torchvision 仍按旧 torch 编译，运行时报 `operator torchvision::nms does not exist`，外层被包成「sentence-transformers 未安装」。匹配的一对是 `torch 2.6.0+cu124` 和 `torchvision 0.21.0+cu124`。

`https://mirrors.aliyun.com/pytorch-wheels/cu124/` 是文件目录，不是 PEP 503 索引，`--index-url` 找不到版本。从 `download.pytorch.org` 拉 nvidia-cudnn 会卡很久。要用 wheel 直链，并且 `--no-deps`。

`docker compose up --force-recreate python-ai` 会丢掉容器里后装的 pip 包。装完 torchvision 之后只能 `docker restart`。为了加入 `HF_HUB_DISABLE_XET` 做过一次 recreate，torchvision 被清掉，需要再装一次。

不关 XET 时，hf-mirror 会把权重重定向到 `cas-bridge.xethub.hf.co`，从国内挂起。第一次问答要先下载大约 2GB 模型。nginx 对 `/api/` 的 `proxy_read_timeout` 是 180 秒，页面会先显示「问答超时」，下载其实还在进行。

浏览器里的 `req-{时间戳}-…` 是前端生成的，python 日志里经常对不上。要在容器日志里搜 `Embedding` 和 `Traceback`。

部门过滤在检索之前。research 只能看 002594 和 601633，rm 只能看 000333 和 000651。空部门不会过滤。库是空的，或者问了没有权限的公司，会得到「当前可访问的知识库中没有检索到足够可靠的证据」。「模型回答，仅供参考」表示这条回复没有引用，也不是问数或 RAG 路由。

### PDF worker

worker 来自 `pdfjs-dist/build/pdf.worker.min.mjs?url`，文件大约 1.2MB，内容是合法的 JavaScript 模块。nginx 1.27 的 `mime.types` 没有 `.mjs`，最初的 `Content-Type` 是 `application/octet-stream`，浏览器拒绝按模块加载，错误是：

```text
Setting up fake worker failed: Failed to fetch dynamically imported module
```

只改 `mime.types` 的那次 sed 没有生效，响应头仍是 `application/octet-stream`。后来用 `location ~* \.mjs$` 把类型设成 `application/javascript` 才对。

类型改对之后，普通窗口仍报同一个错。浏览器按 URL 缓存了第一次的失败响应。文件内容没变时，刷新拿到 304，继续使用旧类型。强制刷新清不掉点开引用之后才发生的动态 `import()`。普通新窗口和旧窗口共用磁盘缓存。无痕窗口没有那份缓存。

第一次点击会先闪出「第 1 / — 页」。那是 PDF 还没画完时的占位页码。`DocumentPdfFrame.vue` 已改成画完再显示页码。不重建 `web` 镜像的话，线上仍是旧页面。

### OpenSandbox

AI Coding 只接受 `opensandbox`。创建失败会报「OpenSandbox 创建失败；未回退到本机 Shell」。沙箱网络拒绝出站，里面不能临时 `pip install` 或 `npm install`。快照也不包含 `.venv` 和 `node_modules`。

`kind.sigs.k8s.io`、`dl.k8s.io`、`get.helm.sh` 从虚拟机上下载会挂起。kind、kubectl、helm 是在 Mac 上下好再 `scp` 上去的。华为云的 kubectl 地址返回过 404。

kind 节点不使用宿主机的 Docker 镜像加速。创建沙箱需要：

- `opensandbox/code-interpreter:v1.1.0`
- `sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/execd:release-1.1.0`
- 同一仓库的 `egress:release-1.1.0`

`code-interpreter` 大约 2.6GB。60 秒内 Pod 一直 Pending、没有 IP，接口返回 `KUBERNETES:POD_READY_TIMEOUT`。宿主机上用 `docker.1ms.run` 拉下了 `opensandbox/code-interpreter:v1.1.0`（镜像 ID `133a3c1720dd`）。镜像只在 Docker 里时，kind 节点仍然没有它。处理命令是 `deploy/opensandbox/load-kind-images.sh`：把 code-interpreter 导入节点，并在节点里拉取 execd 和 egress。

这两条日志可以忽略：FastSandbox informer 的 `sandboxesnapshots` 404，以及 kubectl port-forward 的 `Unsupported upgrade request`。

端口转发在重启后会消失。不要把 8090 和 8091 加进云防火墙。`deploy/opensandbox/.local/` 里的 kubeconfig 和二进制不要提交。

## 当前状态

已经可用：

- http://117.50.46.222/ 可以登录。
- analyst 问比亚迪 2024 车型，RAG 能回到年报第 16 页的证据。
- 无痕窗口可以打开对应 PDF，第 16 / 290 页。

还没有收尾：

- 普通浏览器如果还显示旧的 `pdf.worker.min-….mjs` 错误，说明它仍在用第一次失败的缓存。用无痕窗口，或等 web 镜像重建出新的脚本地址。
- 「第 1 / — 页」的闪烁已在仓库里改掉，线上要按部署命令第 8 节重建 `web` 之后才生效。
- 服务器拉到这份仓库之后，在服务器上执行 `sh deploy/opensandbox/load-kind-images.sh`，沙箱镜像才会进 kind。导入完成前，新建沙箱仍会在 60 秒后超时。
