import pytest

from app.models.base import ChatResult, LLMClient, ModelTimeoutError


def test_chat_result_total_tokens():
    result = ChatResult(content="hi", prompt_tokens=10, completion_tokens=5)
    assert result.total_tokens == 15


def test_llm_client_cannot_instantiate():
    with pytest.raises(TypeError):
        LLMClient()


def test_model_errors_inherit():
    assert issubclass(ModelTimeoutError, Exception)
