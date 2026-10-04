from __future__ import annotations

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from agent.env_utils import get_env, require_env

DEEPSEEK_V4_MAX_TOKENS = 25600
INTENT_MODEL_MAX_TOKENS = 200


def available_agent_models() -> dict[str, tuple[str, str, str]]:
    """只列出已配置凭据的模型，顺序与 RegOps 问答的模型列表一致。"""
    models: dict[str, tuple[str, str, str]] = {}
    providers = (
        ("deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "https://api.deepseek.com",
         "DEEPSEEK_MODEL_IDS", "deepseek-flash,deepseek-v4-pro"),
        ("qwen", "QWEN_API_KEY", "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1",
         "QWEN_MODEL_IDS", "qwen3.8-max,qwen3.8-flash,qwen3.7-plus"),
    )
    for provider, key_name, url_name, default_url, ids_name, default_ids in providers:
        api_key = get_env(key_name).strip()
        if not api_key:
            continue
        base_url = get_env(url_name, default_url).strip()
        configured_ids = dict.fromkeys(
            item.strip() for item in get_env(ids_name, default_ids).split(",") if item.strip()
        )
        for model_id in configured_ids:
            if any(existing.casefold() == model_id.casefold() for existing in models):
                raise ValueError(f"duplicate model ID: {model_id}")
            models[model_id] = (provider, api_key, base_url)
    return models


def default_agent_model_id(models: dict[str, tuple[str, str, str]] | None = None) -> str | None:
    models = available_agent_models() if models is None else models
    preferred = get_env("MAIN_MODEL", "deepseek-v4-pro").strip()
    return preferred if preferred in models else next(iter(models), None)


def require_agent_model_id(model_id: str | None) -> str:
    models = available_agent_models()
    selected = default_agent_model_id(models) if model_id is None else model_id.strip()
    if not selected or selected not in models:
        raise ValueError(f"模型 {selected or '未配置'} 不可用；请从已配置的模型列表中选择")
    return selected


def make_main_model(model_id: str | None = None) -> BaseChatModel:
    """用用户选择的模型构建 DeepAgents 所需的 LangChain ChatModel。"""
    selected = require_agent_model_id(model_id)
    provider, api_key, base_url = available_agent_models()[selected]
    options = dict(
        model=selected,
        model_provider="openai",
        temperature=1.1,
        api_key=api_key,
        base_url=base_url,
        max_tokens=DEEPSEEK_V4_MAX_TOKENS,
        streaming=True,
    )
    if provider == "deepseek":
        options["extra_body"] = {"thinking": {"type": "disabled"}}
    return init_chat_model(**options)


@lru_cache(maxsize=1)
def make_intent_model() -> BaseChatModel:
    """创建用户意图分类专用模型。

    这个模型和主 Agent 模型使用同一套 DeepSeek/OpenAI-compatible 连接配置，
    但参数目标完全不同：

    - 主 Agent 模型负责长上下文推理、工具调用和流式输出，所以 `streaming=True`，
      `max_tokens` 也比较大。
    - 意图分类模型只负责把用户输入归类为固定任务类型，不需要流式输出，也不应该
      产生长文本，因此使用 `streaming=False`、`temperature=0` 和较小的 `max_tokens`。

    单独提供公共函数的好处是：模型初始化逻辑集中在 `agent.core.model`，业务模块
    `task_intent.py` 只关心“如何分类”，不再自己拼装模型连接参数。
    """

    return init_chat_model(
        model=get_env("INTENT_MODEL", get_env("MAIN_MODEL", "deepseek-v4-pro")),
        model_provider="openai",
        temperature=float(get_env("INTENT_MODEL_TEMPERATURE", "0")),
        api_key=require_env("DEEPSEEK_API_KEY"),
        base_url=get_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        max_tokens=int(get_env("INTENT_MODEL_MAX_TOKENS", str(INTENT_MODEL_MAX_TOKENS))),
        streaming=False,
        extra_body={"thinking": {"type": "disabled"}},
    )
