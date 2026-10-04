# W9-3 Langfuse、OTel 与核心指标

> 一次问答能顺着 **W3C `traceparent`** 从 Java 找到 Python，并看到 **Prompt 钉扎版本** 和 **估算成本**。敏感字段进 Trace 前脱敏。

## 跨进程 Trace ID

契约是 **W3C `traceparent`**（`00-{32hex}-{16hex}-{flags}`），不是必须起 Collector。

```text
浏览器 ──X-Request-ID──► Java RequestIdFilter
        ──traceparent──►   缺则补；MDC traceId
                           PythonAiClient 原样转发
                         python-ai ASGI 中间件回写
                           日志 [%(request_id)s] [%(trace_id)s]
                           generation.trace_id / prompt_version / cost_usd
```

CORS 暴露 `X-Request-ID` 和 `traceparent`。Java 日志 `logging.pattern.level` 带 `%X{traceId:-}`。

未配 OpenTelemetry Exporter 时，跨服务追踪仍然成立：同一个 32 位 `trace_id` 出现在两边日志和 `/ops/obs/traces`。

## 本地缓冲 vs Langfuse

| 条件 | 行为 |
|---|---|
| 未配 `LANGFUSE_PUBLIC_KEY` / `SECRET` | 只写入 Python 进程内约 200 条环形缓冲 |
| 配了 Key | 异步 POST `{LANGFUSE_HOST}/api/public/ingestion`（Basic auth）；失败不影响问答 |

成本按公开标价估算（DeepSeek / Qwen 量级 USD / 1M tokens），**不是账单**。问数 0 token 也会留一条，Prompt 版本为空。

前端：运维监控 → **LLM Trace**（`GET /api/ops/obs/overview` · `/api/ops/obs/traces`）。

指标：P95 延迟、流式才有的 TTFT、tokens/s、带 Prompt 版本的占比、估算成本合计。

## 脱敏

进缓冲 / Langfuse 的 input/output 走 `mask_for_log`（身份证、手机号、账号、`sk-`、`DEEPSEEK_API_KEY=`）。证明 Prompt 版本和成本可运营，不等于把 Key 送去第三方。
