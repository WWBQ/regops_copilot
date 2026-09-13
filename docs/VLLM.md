# vLLM 使用手册

> 在自己的 NVIDIA GPU 上把模型跑成 **OpenAI 兼容 HTTP 服务**。不是微调框架，也不替代 RAG / 问数。
>
> 本仓库日常对话仍走 DeepSeek / Qwen **云 API**。粤语模型本机长期用 **Ollama + GGUF**。vLLM 只在**租到带 NVIDIA 的机器**时用。

## 和本机 / 租卡的关系

| 环境 | 能不能跑 vLLM |
|---|---|
| Mac mini（M4，16GB，无 NVIDIA） | **不能**。没有 CUDA。 |
| 算力平台租的 3090（24GB） | **能**。训完、导出后顺手 serve，停租即下线。 |
| 家里常驻 GPU | 目前没有。 |

本机试粤语模型：继续 Ollama。要并发、要和 `/v1/chat/completions` 对齐：再租 3090 起 vLLM。

## 用哪份权重

粤语项目导出链：

```text
yue_qwen_lora（154MB adapter）
  → merged_model/          ← vLLM 用这份（HF 目录，FP16，约 14GB）
  → yue_qwen_q4.gguf       ← Ollama / llama.cpp 用，vLLM 不要当主路径
```

- **用** `merged_model/`（未量化底模合并后的目录）。
- **不要用** 训练时的 4-bit 底模（`unsloth/Qwen2.5-7B-Instruct-bnb-4bit`）。
- **不要用** Q4 GGUF 当 vLLM 主路径（那是 llama.cpp 格式）。
- 合并必须挂在 FP16 的 `Qwen/Qwen2.5-7B-Instruct` 上再 `merge`，原因见 [`INTERVIEW.md`](./INTERVIEW.md) §3.6。

也可不合并：vLLM 加载原版 Qwen，再挂 LoRA。已经合过就优先 serve `merged_model/`。

## 租卡上安装

需要：Linux + NVIDIA 驱动 + CUDA 可用（`nvidia-smi` 能看到 3090）。

```bash
# 建议独立 venv，避免和训练环境搅在一起
python3 -m venv .venv-vllm
source .venv-vllm/bin/activate
pip install -U pip
pip install vllm
```

装完检查：

```bash
nvidia-smi
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

第一项必须是 GPU；第二项必须是 `True` 和 `NVIDIA GeForce RTX 3090`（或平台给的同级卡）。

## 启动

把路径换成平台上 `merged_model` 的实际位置：

```bash
vllm serve /path/to/merged_model \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype float16 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 4096 \
  --served-model-name yue-qwen
```

| 参数 | 作用 |
|---|---|
| `--dtype float16` | 7B FP16，3090 24GB 够用 |
| `--gpu-memory-utilization 0.90` | 给 KV cache 留显存；OOM 就降到 `0.80` |
| `--max-model-len 4096` | 上下文上限。再大占显存。演示 4k 够 |
| `--served-model-name` | curl 里 `model` 字段用这个名字 |

未合并、只挂 LoRA 时：

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --enable-lora \
  --lora-modules yue=/path/to/yue_qwen_lora \
  --dtype float16 \
  --max-model-len 4096 \
  --served-model-name yue-qwen
```

日志出现 `Uvicorn running` / `Application startup complete` 再测。默认监听 `http://<机器IP>:8000`。平台若要映射端口，按控制台给的公网地址改下面的 URL。

## 量大时怎么调

先分清「量大」是哪一种。显存就那么多：权重约占 14GB，剩下的给 **KV cache**（每条正在生成的对话都要占一块）。人多和单条特别长，抢的是同一块显存。

| 量大指什么 | 优先动什么 | 要牺牲什么 |
|---|---|---|
| 很多人同时问，每条不长 | 提高同时在跑的条数 | 单条上下文不能太长 |
| 单条特别长（整篇年报塞进 prompt） | 提高 `--max-model-len` | 同时能跑的人数变少 |
| 同一段 system / 检索前缀反复出现 | 打开前缀缓存 | 多占一点显存 |

**3090 + 7B FP16 可抄的三档**（路径仍换成你的 `merged_model`）：

人多、题短（压测、多人试用）：

```bash
vllm serve /path/to/merged_model \
  --host 0.0.0.0 --port 8000 \
  --dtype float16 \
  --served-model-name yue-qwen \
  --gpu-memory-utilization 0.92 \
  --max-model-len 2048 \
  --max-num-seqs 64 \
  --enable-prefix-caching \
  --enable-chunked-prefill
```

长短都有（默认往这档靠）：

```bash
vllm serve /path/to/merged_model \
  --host 0.0.0.0 --port 8000 \
  --dtype float16 \
  --served-model-name yue-qwen \
  --gpu-memory-utilization 0.90 \
  --max-model-len 4096 \
  --max-num-seqs 32 \
  --enable-prefix-caching \
  --enable-chunked-prefill
```

单条要很长（少人、长文）：

```bash
vllm serve /path/to/merged_model \
  --host 0.0.0.0 --port 8000 \
  --dtype float16 \
  --served-model-name yue-qwen \
  --gpu-memory-utilization 0.88 \
  --max-model-len 8192 \
  --max-num-seqs 8 \
  --enable-chunked-prefill
```

| 参数 | 调大之后 | 调小之后 |
|---|---|---|
| `--max-num-seqs` | 同时处理更多请求，排队少 | 显存更稳，延迟可能变高（排队） |
| `--max-model-len` | 单条 prompt+回复能更长 | 同一块显存能塞进更多并发 |
| `--gpu-memory-utilization` | KV cache 更大，并发/长度都更宽裕 | 更不容易启动 OOM |
| `--enable-prefix-caching` | 相同前缀（system、同一批 RAG 片段）少算一遍 | 几乎总该开；前缀都不重复时没收益 |
| `--enable-chunked-prefill` | 长 prompt 不会把短请求堵死 | 极短请求为主时收益小 |
| `--max-num-batched-tokens` | 每步算更多 token，吞吐上去 | 默认即可；OOM 再降（如 `4096`） |

请求体也要收：调用方设合理的 `max_tokens`（回复上限）。客户端乱写 `max_tokens: 4096`，KV 会按上限预留，并发立刻掉下来。粤语对照 256～512 够用。

**怎么知道调没调对**

另开一个终端看 `nvidia-smi`：显存长期 95% 以上还频繁抢不到位 → 降 `seqs` 或 `max-model-len`。利用率只有 40%、请求在排队 → 可以提高 `seqs`。vLLM 日志里的排队数、吞吐（tokens/s）比只看延迟准。

单卡 3090 不要上 `--tensor-parallel-size`（那是多卡切一层）。一张卡吃不消就：**前面加排队**（应用层限流），或再租一张卡各起一个 vLLM，而不是在一张卡上把 `max-model-len` 和 `max-num-seqs` 同时拉满。

合规问答若真走自建推理：长上下文应靠 **RAG 只塞 top-k 片段**，不要把 300 页 PDF 塞进 vLLM。那是应用设计，不是再调一个参数。

## 试通

```bash
curl -s http://127.0.0.1:8000/v1/models

curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "yue-qwen",
    "messages": [
      {"role": "system", "content": "你是粤语助手。用粤语回答，不要把提问当成翻译任务。"},
      {"role": "user", "content": "点解香港叫香江？"}
    ],
    "temperature": 0.3,
    "max_tokens": 256
  }'
```

看三件事：`choices[0].message.content` 有没有字、是不是又把问题译成普通话、`usage` 里的 token。

停服务：终端 `Ctrl+C`。**用完在平台上关机/释放实例**，否则继续按小时计费。

## 和 API、Ollama 怎么选

| | 干什么 | 什么时候用 |
|---|---|---|
| DeepSeek / Qwen API | 云上模型，按 Token 付钱 | RegOps 日常问答 |
| Ollama + Q4 GGUF | 本机 Mac 随手起 | 没租卡时跑粤语模型 |
| vLLM + `merged_model/` | 租卡上高并发、OpenAI 接口 | 对照吞吐、或必须内网推理 |

应用层（检索、问数、工单）不用为 vLLM 重写。它只是换了一个「说话地址」。

## 接到 RegOps（现状）

`python-ai` 的 `get_llm_client()` 只认 `deepseek` / `qwen`，地址写死在客户端里（DeepSeek → `https://api.deepseek.com`）。**现在没有「填一个 vLLM URL 就切过去」的环境变量。**

要对照时：

1. 在租卡上 `curl` vLLM，和 Ollama / 云 API 比同一批粤语题（口吻、会不会乱翻译）。
2. 真要让合规问答走 vLLM：给 `DeepSeekClient` 增加可配置 `base_url` / `model`，指向 `http://<vLLM>:8000`，`model` 填 `yue-qwen`，API Key 可填任意非空占位（vLLM 默认不校验）。这是改代码，不是手册里一条命令。

不要把粤语权重接到 RegOps 年报问答上充「更懂财报」——SFT 改的是怎么答，不补年报知识。数字和出处仍走问数 / RAG。

## 常见问题

| 现象 | 处理 |
|---|---|
| `torch.cuda.is_available()` 为 False | 不是这台 Mac；或租卡镜像没装对 CUDA |
| 启动后立刻 OOM | 降 `--gpu-memory-utilization`，或把 `--max-model-len` 改成 2048 |
| 一压测就排队 / 超时 | 先降调用方 `max_tokens`；再降 `--max-model-len` 或 `--max-num-seqs`，不要两个一起加 |
| 显存很空但很慢 | 提高 `--max-num-seqs`，打开 `--enable-prefix-caching` |
| curl 404 / 连不上 | 看平台端口映射；本机试必须用实例的 IP，不是家里的 localhost |
| 回复又在翻译 | 推理侧 system 写清「不要把提问当成翻译」；这是已知行为，不是 vLLM 配错 |
| 想用 GGUF | 走 Ollama，不要硬塞给 vLLM |

## 面试三句

1. vLLM 是推理服务：自己的卡、连续批处理，对外 OpenAI 兼容接口。
2. 粤语模型 serve 的是合并后的 HF 目录，不是训练用的 4-bit，也不是给 Ollama 的 GGUF。
3. 本机没有常驻 GPU；vLLM 只在租卡窗口跑，停租即下线。Mac 用 Ollama，RegOps 现网仍走云 API。
