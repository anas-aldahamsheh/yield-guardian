"""Response parsing: completions, usage, tool calls, stream accumulation."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.llm.helpers import load_cassette
from yield_guardian.llm.errors import ResponseShapeError
from yield_guardian.llm.profiles import Usage
from yield_guardian.llm.results import (
    ChatResult,
    StreamAccumulator,
    parse_chat_completion,
    parse_usage,
)


def fixture_body(name: str, index: int = 0) -> Any:
    return load_cassette(name).interactions[index].response.json_body


def test_text_completion_with_zero_reasoning_breakdown() -> None:
    parsed = parse_chat_completion(fixture_body("chat_text_deepseek"))
    assert parsed.content == "Fixture reply: hello from the test double."
    assert parsed.reasoning is None
    assert parsed.finish_reason == "stop"
    assert parsed.served_model == "DeepSeek-V4-Flash"
    assert parsed.response_id == "chatcmpl-fixture-text-1"
    assert parsed.usage == Usage(
        prompt_tokens=120, completion_tokens=30, total_tokens=150, reasoning_tokens=0
    )


def test_reasoning_text_and_counts_including_cached_prompt_tokens() -> None:
    parsed = parse_chat_completion(fixture_body("chat_reasoning_glm"))
    assert parsed.reasoning is not None
    assert parsed.reasoning.startswith("Fixture thinking text")
    assert parsed.usage is not None
    assert parsed.usage.reasoning_tokens == 300
    assert parsed.usage.cached_tokens == 500


def test_missing_reasoning_count_stays_unknown() -> None:
    parsed = parse_chat_completion(fixture_body("chat_qwen27b_no_reasoning_count"))
    assert parsed.usage is not None
    assert parsed.usage.reasoning_tokens is None
    assert parsed.usage.completion_tokens == 200


def test_parallel_tool_calls_are_parsed_in_order() -> None:
    parsed = parse_chat_completion(fixture_body("chat_tool_calls_deepseek"))
    assert parsed.content is None
    assert parsed.finish_reason == "tool_calls"
    assert [(c.id, c.function.name) for c in parsed.tool_calls] == [
        ("call_fixture_1", "get_shap"),
        ("call_fixture_2", "get_contributions"),
    ]
    assert parsed.tool_calls[0].function.arguments == '{"unit_id": 7, "top_k": 5}'


def test_tool_call_arguments_given_as_an_object_are_serialised() -> None:
    body = {
        "choices": [
            {
                "message": {
                    "tool_calls": [{"function": {"name": "get_risk", "arguments": {"unit_id": 3}}}]
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    (call,) = parse_chat_completion(body).tool_calls
    assert call.id == "call_0"
    assert call.function.arguments == '{"unit_id":3}'


def test_vllm_reasoning_content_alias_is_accepted() -> None:
    body = {"choices": [{"message": {"content": "x", "reasoning_content": "thought"}}]}
    assert parse_chat_completion(body).reasoning == "thought"


def test_empty_content_with_length_is_an_empty_truncated_result() -> None:
    parsed = parse_chat_completion(fixture_body("chat_length_empty"))
    result = ChatResult(
        model="MiMo-V2.6-Flash", content=parsed.content, finish_reason=parsed.finish_reason
    )
    assert result.is_empty
    assert result.truncated
    assert not ChatResult(model="m", content="  ", tool_calls=()).truncated


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"choices": []},
        {"choices": ["x"]},
        {"choices": [{"delta": {}}]},
        {"choices": [{"message": {"tool_calls": "nope"}}]},
        {"choices": [{"message": {"tool_calls": [{"function": {}}]}}]},
    ],
)
def test_malformed_completions_raise_shape_errors(body: object) -> None:
    with pytest.raises(ResponseShapeError):
        parse_chat_completion(body)


def test_usage_ignores_non_integer_counts() -> None:
    assert parse_usage({"prompt_tokens": True, "completion_tokens": "7"}) is None
    assert parse_usage({"prompt_tokens": 10.0}) == Usage(prompt_tokens=10)
    assert parse_usage("usage") is None


def stream_chunks(name: str) -> list[Any]:
    sse = load_cassette(name).interactions[0].response.sse
    assert sse is not None
    return [json.loads(data) for data in sse if data != "[DONE]"]


def test_stream_accumulator_folds_reasoning_content_finish_and_usage() -> None:
    accumulator = StreamAccumulator()
    types: list[str] = []
    for chunk in stream_chunks("stream_text_qwen"):
        types.extend(delta.type for delta in accumulator.feed(chunk))
    assert types == ["reasoning", "content", "content", "finish", "usage"]
    parsed = accumulator.result()
    assert parsed.content == "Fixture answer, T² chart."
    assert parsed.reasoning == "Fixture thinking."
    assert parsed.finish_reason == "stop"
    assert parsed.usage is not None
    assert parsed.usage.reasoning_tokens == 5
    assert parsed.response_id == "chatcmpl-fixture-stream-1"


def test_stream_without_usage_leaves_usage_unknown() -> None:
    accumulator = StreamAccumulator()
    for chunk in stream_chunks("stream_no_usage"):
        accumulator.feed(chunk)
    assert accumulator.result().usage is None


def test_streamed_tool_call_fragments_are_joined() -> None:
    accumulator = StreamAccumulator()
    for chunk in stream_chunks("stream_tool_calls"):
        accumulator.feed(chunk)
    parsed = accumulator.result()
    (call,) = parsed.tool_calls
    assert call.id == "call_stream_1"
    assert call.function.name == "get_risk"
    assert call.function.arguments == '{"unit_id": 7}'
    assert parsed.finish_reason == "tool_calls"


def test_a_streamed_tool_call_without_a_name_is_a_shape_error() -> None:
    accumulator = StreamAccumulator()
    accumulator.feed({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c"}]}}]})
    with pytest.raises(ResponseShapeError):
        accumulator.result()


def test_a_stream_chunk_that_is_not_an_object_is_a_shape_error() -> None:
    with pytest.raises(ResponseShapeError):
        StreamAccumulator().feed(["not", "an", "object"])
