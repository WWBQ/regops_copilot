import pytest

from app.models.llm import ChatResult, LLMClient, ModelTimeoutError


def test_chat_result_total_tokens():
    result = ChatResult(content="hi", prompt_tokens=10, completion_tokens=5)
    assert result.total_tokens == 15


def test_llm_client_requires_api_key():
    with pytest.raises(ValueError, match="API key"):
        LLMClient(api_key="", base_url="https://example.com", model_id="demo", timeout=1)


def test_model_errors_inherit():
    assert issubclass(ModelTimeoutError, Exception)
