# 云 GPU 虚拟机部署记录

这是 2026-10-11 把 RegOps Copilot 部署到一台租用的 RTX 3090 虚拟机上的实际过程。记录的是当时执行过、并且最后走通的命令，以及中间踩过的坑。不是从零开始的通用安装手册。

站点地址：http://117.50.46.222/

演示账号：

| 用户 | 密码 | 部门 | 能看的公司 |
| --- | --- | --- | --- |
| analyst | analyst123 | research | 002594、601633 |
| rm | rm123 | rm | 000333、000651 |
| admin | admin123 | compliance | 全部七家 |

两条贯穿全程的规则：

- Mac 终端的提示符是 `chengfeng@…`。服务器终端的提示符是 `ubuntu@10-60-252-39`。两边的命令不能贴错地方。
- 云防火墙只放行 22、80、443。不要开放 5432、8000、8080、2024、8090、8091。

## 1. 机器

选这台是因为 4 核 16G 同时跑 BGE 向量、bge-reranker 精排和 PDF 解析太紧。vLLM 只能替换对话大模型，替换不了 BGE、精排和 MinerU。

| 项 | 值 |
| --- | --- |
| 实例 | regops，uhost-1wc4ao9u5div |
| 系统 | Ubuntu 22.04，用户 `ubuntu` |
| 配置 | RTX 3090 24GB，16 核，64GB 内存，100GB 磁盘 |
| 公网 | 117.50.46.222 |
| 内网 | 10.60.252.39 |
| Docker 网关 | 172.18.0.1 |
| 连接 | `ssh ubuntu@117.50.46.222` |

关机后 GPU 不计费，但库存可能被别人拿走。

## 2. 显卡驱动

新系统里没有 `nvidia-smi`，也没有 Docker。

```bash
sudo apt-get update
sudo apt-get install -y nvidia-driver-550
sudo reboot
```

装驱动时 apt 会弹出 “Daemons using outdated libraries”，选 Ok。SSH 断开是重启的正常现象，等一会儿再连。

```bash
nvidia-smi
```

成功时能看到 RTX 3090，驱动 580.178.04，显存 24576 MiB。

坑：重启命令必须在服务器上执行。有一次 `sudo reboot` 贴进了 Mac 终端。

## 3. Docker 和 GPU 容器

阿里云 docker-ce 源在这台机器上没有可安装的候选包（`docker.list` 没真正生效，apt 只看得到 `mirrors.ucloud.cn`）。改用 Ubuntu 自带的 Docker。

```bash
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker ubuntu
```

退出 SSH 再登录，让 `docker` 组生效。Compose 版本是 v2.40.3。

NVIDIA 容器运行时用官方源安装。`tee` 那行如果被终端折行，软件源会写坏，要重贴完整命令：

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

Docker Hub 从这台机器直连会超时。写镜像加速时要保留 `nvidia-ctk` 已经写好的 nvidia runtime，不能把 `daemon.json` 整文件覆盖掉。

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
```

验证 GPU 能进容器：

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

第一次拉 `nvidia/cuda` 会在 `registry-1.docker.io` 超时。配好镜像加速后再跑一次，应能看到 3090。

## 4. 代码和环境变量

仓库是私有的。在服务器上匿名 `git clone` 会 404，并停在 GitHub 用户名提示。需要能访问 `WWBQ/regops_copilot` 的账号。多行脚本贴进去时，用户名提示会把后面的行吃掉，先 Ctrl+C 再重来。

```bash
git clone git@github.com:WWBQ/regops_copilot.git ~/regops_copilot
```

`.env` 在 Mac 上，不在服务器上。`scp` 必须在 Mac 执行：

```bash
scp /Users/chengfeng/Desktop/AI/regops_copilot/.env ubuntu@117.50.46.222:~/regops_copilot/.env
```

不要把 `.env` 提交进 Git。里面有 API Key。Compose 会覆盖容器里的 `DATABASE_URL`，宿主机 `.env` 里的本机数据库口令不会直接给容器用。

服务器上的 `.env` 后来改过这些项：

```bash
EMBEDDING_LOCAL_FILES_ONLY=false
HF_ENDPOINT=https://hf-mirror.com
HF_HUB_DISABLE_XET=1
STARTUP_WARMUP_ENABLED=false
AI_CODING_EXECUTION_BACKEND=opensandbox
AI_CODING_SANDBOX_DOMAIN=172.18.0.1:8090
AI_CODING_SANDBOX_PROTOCOL=http
```

`AI_CODING_SANDBOX_API_KEY` 用服务器上 `~/sandbox-api-key.txt` 的值，不要把密钥贴进聊天或文档。

坑：

- Mac 上原来的 `AI_CODING_EXECUTION_BACKEND=opensandbox` 指向 Mac 的 kind。第一次部署脚本把它改成了 `local`，当前代码只接受 `opensandbox`，会直接报「不会回退到本机执行」。
- `EMBEDDING_LOCAL_FILES_ONLY` 默认是 true，服务器上没有预先放好的模型文件，必须改成 false。
- 启动预热会在 `/health` 之前下载模型，健康检查一直起不来。服务器上关掉 `STARTUP_WARMUP_ENABLED`。

## 5. Compose

仓库里的 `compose.yaml` 把网页映射成 `8088:80`。这台机器的防火墙只放行 80，所以服务器上的端口要改成 `80:80`。`python-ai` 和 `ingest-worker` 要加 `gpus: all`。这两处目前只改在服务器检出上，Git 里的 `compose.yaml` 仍是 `8088:80`、没有 GPU 段。

国内构建时 Debian 和 Ubuntu 官方源很慢。服务器上的 `python-ai/Dockerfile`、`java-service/Dockerfile` 把 apt 换成了 `mirrors.aliyun.com`，pip 使用 `https://pypi.tuna.tsinghua.edu.cn/simple`。这些 Dockerfile 改动也只在服务器检出里。

```bash
cd ~/regops_copilot
docker compose build
docker compose up -d
```

第一次构建走 `deb.debian.org`，跑了约 92 分钟还停在 apt，手动停掉后换源重建才成功。成功后的容器：

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

浏览器打开 http://117.50.46.222/ 。db 和 java 虽然在容器里发布了 5432 和 8080，防火墙不要放行。

## 6. 数据库和年报原件

刚起来的库只有表结构、Java 种子用户和问数别名。后来导入的数据是 `pdf_document` 12 行、`doc_chunks` 12441 行。

年报 PDF 字节不在数据库里，在对象存储。键是 `reports/{doc_id}/{hash}.pdf`，桶名 `regops-docs`。Mac 上的文件在仓库的 `data/objects`（约 181MB）。容器里的目录是 `/app/data/objects`，卷名 `regops_copilot_python_data`。

在 Mac 上把对象传到服务器，再在服务器上拷进容器：

```bash
# Mac
rsync -a data/objects/ ubuntu@117.50.46.222:~/regops-objects/
```

```bash
# 服务器
docker cp ~/regops-objects/. regops-python:/app/data/objects/
```

拷贝之前，预览接口返回 404，页面文案是「年报源文件不存在或已移除」。拷贝之后这个错误消失。

## 7. 让 RAG 真正跑起来

页面能开之后，问答依次出现过这些现象：`stream failed`、问答服务连不上、问答超时、一直停在「正在回复…」、以及「模型回答，仅供参考」。浏览器里的 `req-{时间戳}-…` 是前端自己生成的，python 日志里经常对不上。要在容器日志里搜 `Embedding` 和 `Traceback`。

### torchvision 和 torch 不匹配

`python-ai/Dockerfile` 先装 `requirements.txt`，再从 cu124 强制重装 torch。sentence-transformers 带进来的 torchvision 还是按旧 torch 编译的，运行时报：

```text
RuntimeError: operator torchvision::nms does not exist
```

这会被包成一句误导性的「sentence-transformers 未安装」。匹配的一对是 `torch 2.6.0+cu124` 和 `torchvision 0.21.0+cu124`。

阿里云的 `https://mirrors.aliyun.com/pytorch-wheels/cu124/` 是文件目录，不是 PEP 503 索引，`--index-url` 会显示找不到版本。从美国的 `download.pytorch.org` 拉 nvidia-cudnn 会卡很久。正确做法是用 wheel 的直链，并且 `--no-deps`：

```bash
docker exec -it regops-python pip install --no-deps \
  https://download.pytorch.org/whl/cu124/torchvision-0.21.0%2Bcu124-cp312-cp312-linux_x86_64.whl
docker restart regops-python
```

坑：`docker compose up --force-recreate python-ai` 会丢掉容器里后装的 pip 包。装完 torchvision 之后只能 `docker restart`，不能 recreate。后来为了加 `HF_HUB_DISABLE_XET` 做过一次 recreate，torchvision 被清掉，需要再装一次。

确认版本：

```bash
docker exec regops-python python -c "import torch, torchvision; print(torch.__version__, torchvision.__version__)"
```

期望是 `2.6.0+cu124` 和 `0.21.0+cu124`。

### Hugging Face 镜像和 XET

不关 XET 时，hf-mirror 会把权重重定向到 `cas-bridge.xethub.hf.co`，从国内挂起。第一次问答要先把大约 2GB 的模型拉下来，nginx 对 `/api/` 的 `proxy_read_timeout` 是 180 秒，所以页面先显示「问答超时」，下载其实还在进行。

`.env` 里要有：

```bash
HF_ENDPOINT=https://hf-mirror.com
HF_HUB_DISABLE_XET=1
```

改完环境变量需要 recreate 才能进容器，而 recreate 会清掉 torchvision，所以顺序是：先改 `.env` 并 recreate，再重新 pip 装 torchvision，最后只 restart。

模型可以在容器里预先加载，这条命令不受 HTTP 180 秒限制：

```bash
docker exec -it regops-python python -c "
from sentence_transformers import SentenceTransformer, CrossEncoder
SentenceTransformer('BAAI/bge-m3', device='cuda')
CrossEncoder('BAAI/bge-reranker-v2-m3', device='cuda')
print('ready')
"
```

部门过滤在检索之前。research 只能看 002594 和 601633，rm 只能看 000333 和 000651，空部门不会过滤。库是空的，或者问了没有权限的公司，会得到「当前可访问的知识库中没有检索到足够可靠的证据」。「模型回答，仅供参考」表示这条回复没有引用，也不是问数或 RAG 路由。

这一步走通的标志：用 analyst 问「比亚迪2024年发布了哪些车型」，证据面板能出现年报第 16 页的原文。

## 8. PDF 预览

文本在 Postgres 里，原件在对象存储里。对象拷进容器之后，错误从「年报源文件不存在」变成 pdf.js：

```text
Setting up fake worker failed: Failed to fetch dynamically imported module:
http://117.50.46.222/assets/pdf.worker.min-….mjs
```

worker 由 `web/src/components/documents/DocumentPdfFrame.vue` 以 `pdfjs-dist/build/pdf.worker.min.mjs?url` 引入。文件本身是合法的 JavaScript 模块，大约 1.2MB。nginx 1.27 的 `mime.types` 没有 `.mjs`，所以最初的 `Content-Type` 是 `application/octet-stream`。浏览器拒绝把它当模块加载。

只改 `mime.types` 的那次 sed 没有生效，响应头仍是 `application/octet-stream`。后来在服务器容器的 `/etc/nginx/conf.d/default.conf` 里加了：

```nginx
location ~* \.mjs$ {
    default_type application/javascript;
    try_files $uri =404;
}
```

```bash
docker exec regops-web nginx -t
docker exec regops-web nginx -s reload
curl -sI http://127.0.0.1/assets/pdf.worker.min-CjEcRF4W.mjs | head
```

响应应是 `HTTP/1.1 200` 和 `Content-Type: application/javascript`。仓库里的 `web/nginx.conf` 也加了同样的 location。正在跑的容器是当场改的，不重建 `web` 镜像的话，以容器里的配置为准。

类型改对之后，普通窗口仍报同一个错。原因是浏览器把第一次失败的响应按 URL 缓存了。文件内容没变时，刷新拿到的是 304，继续使用旧的 `application/octet-stream`。强制刷新也清不掉后来才发生的动态 `import()`：年报 worker 是点开引用之后才请求的。

处理：

1. 把 worker 复制成一个新的 `.js` 地址，并让首页脚本指向新的包，绕开旧缓存。
2. 用无痕窗口打开 http://117.50.46.222/index.html 。无痕窗口没有那份失败缓存。普通新窗口会共用同一份磁盘缓存。

无痕窗口里可以打开第 16 页，总页数 290。

第一次点击会先闪出「第 1 / — 页」。那是 PDF 还没画完时的占位页码，不是再次加载失败。本地 `DocumentPdfFrame.vue` 已改成画完当前页再显示页码，中间文案是「正在打开第 N 页…」。这处改动还要重建 web 镜像才会出现在线上：

```bash
# Mac
scp web/src/components/documents/DocumentPdfFrame.vue \
  ubuntu@117.50.46.222:~/regops_copilot/web/src/components/documents/DocumentPdfFrame.vue
scp web/nginx.conf ubuntu@117.50.46.222:~/regops_copilot/web/nginx.conf
```

```bash
# 服务器
cd ~/regops_copilot
docker compose build web
docker compose up -d web
```

只重建 `web`。不要 `--force-recreate python-ai`。

## 9. OpenSandbox

AI Coding 的当前代码只接受 `opensandbox`。创建失败会报「OpenSandbox 创建失败；未回退到本机 Shell」，不会改在宿主机上执行。沙箱网络是拒绝出站的，所以沙箱里不能临时 `pip install` / `npm install`。快照也不包含 `.venv` 和 `node_modules`。

这台机器上的控制平面：

| 项 | 值 |
| --- | --- |
| kind 集群 | `regops-sandbox`，context `kind-regops-sandbox` |
| 命名空间 | `opensandbox-system`、`opensandbox` |
| 版本 | Helm chart `release-1.1.0` |
| 工具 | kind v0.33.0、kubectl v1.32.2、helm v3.22.0，装在 `/usr/local/bin` |
| 网关 | `172.18.0.1:8091`，给 Compose 网络里的 risk-agent 用 |
| 端口转发 | `8090` 到 opensandbox-server，`8091` 到 ingress-gateway，监听 `0.0.0.0` |

`kind.sigs.k8s.io`、`dl.k8s.io`、`get.helm.sh` 从虚拟机上下载会挂起。kind、kubectl、helm 是在 Mac 上下好再 `scp` 上去的。华为云的 kubectl 地址返回过 404。

kind 节点不会使用宿主机的 Docker 镜像加速。创建沙箱时要的镜像是：

- `opensandbox/code-interpreter:v1.1.0`
- `sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/execd:release-1.1.0`
- 同一仓库的 `egress:release-1.1.0`

`code-interpreter` 大约 2.6GB。60 秒内 Pod 一直 Pending、没有 IP，接口返回 `KUBERNETES:POD_READY_TIMEOUT`。宿主机上用 `docker.1ms.run` 把 `opensandbox/code-interpreter:v1.1.0` 拉下来了（镜像 ID `133a3c1720dd`）。`docker save | ctr import` 进 kind 节点，以及在 kind 节点里拉取 execd / egress，这一步还没有做完。所以 AI Coding 的控制平面是通的（`127.0.0.1:8090/health` 返回 200，容器也能访问 `172.18.0.1:8090`），但新建沙箱仍会超时。

这些日志不是根因，可以忽略：

- FastSandbox informer 的 `sandboxesnapshots` 404
- kubectl port-forward 的 `Unsupported upgrade request`

端口转发在重启后会消失，需要重新挂上。不要把 8090 和 8091 加进云防火墙。`deploy/opensandbox/.local/` 里的 kubeconfig 和二进制不要提交。

## 10. 现在的状态

已经可用：

- http://117.50.46.222/ 可以登录。
- analyst 问比亚迪 2024 车型，RAG 能回到年报第 16 页的证据。
- 无痕窗口可以打开对应 PDF，第 16 / 290 页。

还没有收尾：

- 普通浏览器如果还显示旧的 `pdf.worker.min-….mjs` 错误，说明它仍在用第一次失败的缓存。用无痕窗口，或等 web 镜像重建出新的脚本地址。
- 「第 1 / — 页」的闪烁已在本地改掉，线上要按第 8 节重建 `web` 之后才生效。
- AI Coding 还要把 `code-interpreter`、execd、egress 导入 kind，沙箱才能在 60 秒内变成 Running。
- 服务器上的 apt 源、pip 源、`80:80`、`gpus: all`、torchvision 直链，都还没写回 Git。下次用仓库里的 Dockerfile 无缓存重建，会回到官方源，也会再次拆开 torch 和 torchvision。

## 11. 下次关机后再开机

在云控制台开机，等一会儿再连。关机只停计费，磁盘还在，不要删实例。删掉之后数据库、模型缓存和年报原件都没了。

下面的命令都在服务器上执行，提示符是 `ubuntu@10-60-252-39`：

```bash
ssh ubuntu@117.50.46.222
nvidia-smi
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Compose 服务写了 `restart: unless-stopped`。`regops-web`、`regops-python`、`regops-java`、`regops-db` 都是 Up 之后，直接打开 http://117.50.46.222/ 。第一次提问会把 BGE 和精排模型载入显卡，可能要等一会儿，模型文件还在数据卷里，不会重新下载。

如果这几个容器是 Exited，只把原来的容器拉起来：

```bash
cd ~/regops_copilot
docker compose up -d
```

不要加 `--build`，也不要 `--force-recreate`。`python-ai` 一旦按镜像重建，容器里后装的 `torchvision 0.21.0+cu124` 会丢，问答会再次报 `torchvision::nms`。真的被重建过，才按第 7 节重新安装 torchvision，然后只执行 `docker restart regops-python`。

问答和年报预览不依赖 OpenSandbox。kind 节点和两条端口转发会随关机消失，只有再用 AI Coding 时才需要补：

```bash
docker start regops-sandbox-control-plane
kubectl get nodes
nohup kubectl -n opensandbox-system port-forward --address 0.0.0.0 service/opensandbox-server 8090:80 > /tmp/sb-server.log 2>&1 &
nohup kubectl -n opensandbox-system port-forward --address 0.0.0.0 service/opensandbox-ingress-gateway 8091:80 > /tmp/sb-gateway.log 2>&1 &
curl -s http://127.0.0.1:8090/health
```

`/health` 返回 200 表示沙箱 API 已恢复。不要把 8090 和 8091 加进云防火墙。
