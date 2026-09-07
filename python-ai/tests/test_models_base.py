import pytest

from app.models.base import ChatResult, LLMClient, ModelTimeoutError
from app.models.openai_compat import OpenAIStreamAccumulator, parse_chat_completion, parse_sse_data_line


def test_chat_result_total_tokens():
    result = ChatResult(content="hi", prompt_tokens=10, completion_tokens=5)
    assert result.total_tokens == 15


def test_llm_client_cannot_instantiate():
    with pytest.raises(TypeError):
        LLMClient()


def test_model_errors_inherit():
    assert issubclass(ModelTimeoutError, Exception)


def test_parse_chat_completion_tool_calls():
    result = parse_chat_completion(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {
                                    "name": "list_scope",
                                    "arguments": '{"year":2024}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3},
        },
        12.5,
    )
    assert result.content == ""
    assert result.tool_calls[0].name == "list_scope"
    assert result.tool_calls[0].arguments == {"year": 2024}
    assert result.total_tokens == 12


def test_parse_sse_data_line():
    assert parse_sse_data_line("data: {\"a\":1}") == '{"a":1}'
    assert parse_sse_data_line("data: [DONE]") == "[DONE]"
    assert parse_sse_data_line(": keep-alive") is None
    assert parse_sse_data_line("event: delta") is None


def test_stream_accumulator_joins_deltas_and_usage():
    acc = OpenAIStreamAccumulator()
    assert acc.apply({"choices": [{"delta": {"content": "你"}}]}) == "你"
    assert acc.apply({"choices": [{"delta": {"content": "好"}}]}) == "好"
    acc.apply({"usage": {"prompt_tokens": 4, "completion_tokens": 2}, "choices": [{"delta": {}}]})
    result = acc.result(12.0)
    assert result.content == "你好"
    assert result.prompt_tokens == 4
    assert result.completion_tokens == 2
    assert result.latency_ms == 12.0
