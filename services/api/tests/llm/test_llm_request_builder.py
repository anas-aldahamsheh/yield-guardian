"""The request builder enforces each model's documented rules before anything is sent."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from yield_guardian.llm.errors import ProfileViolationError
from yield_guardian.llm.messages import (
    ChatMessage,
    ChatRequest,
    FunctionCall,
    FunctionSpec,
    ImagePart,
    ImageUrl,
    NamedFunction,
    NamedToolChoice,
    ResponseFormat,
    TextPart,
    ToolCall,
    ToolSpec,
)
from yield_guardian.llm.profiles import DOCUMENTED_PROFILES, ModelProfile, conservative_profile
from yield_guardian.llm.request_builder import IMAGE_REMOVED_NOTE, build_chat_request

IMAGE = ImagePart(image_url=ImageUrl(url="data:image/png;base64,iVBORw0KGgo="))
TOOL = ToolSpec(
    function=FunctionSpec(
        name="get_risk",
        description="Read the risk of a unit.",
        parameters={"type": "object", "properties": {"unit_id": {"type": "integer"}}},
    )
)


def profile(model: str) -> ModelProfile:
    return DOCUMENTED_PROFILES[model]


def request(*messages: ChatMessage, **params: Any) -> ChatRequest:
    return ChatRequest(messages=messages, max_tokens=params.pop("max_tokens", 256), **params)


def roles(body: dict[str, Any]) -> list[str]:
    return [m["role"] for m in body["messages"]]


# --- system and developer messages ------------------------------------------------------------


def test_qwen_flash_next_merges_every_system_and_developer_message_into_one_first() -> None:
    built = build_chat_request(
        profile("Qwen3.8-Flash-Next"),
        request(
            ChatMessage.user("question"),
            ChatMessage.system("rules A"),
            ChatMessage.developer("rules B"),
            ChatMessage.system("rules C"),
        ),
    )
    assert roles(built.body) == ["system", "user"]
    assert built.body["messages"][0]["content"] == "rules A\n\nrules B\n\nrules C"
    assert any("merged 3" in note for note in built.adjustments)
    assert any("developer" in note for note in built.adjustments)


def test_qwen_flash_next_requires_a_system_message() -> None:
    with pytest.raises(ProfileViolationError) as caught:
        build_chat_request(profile("Qwen3.8-Flash-Next"), request(ChatMessage.user("hi")))
    assert caught.value.rule == "system_message"


def test_a_single_first_system_message_is_left_untouched() -> None:
    built = build_chat_request(
        profile("Qwen3.8-Flash-Next"), request(ChatMessage.system("s"), ChatMessage.user("u"))
    )
    assert roles(built.body) == ["system", "user"]
    assert built.adjustments == ()


def test_qwen_27b_allows_no_system_message_and_merges_several() -> None:
    no_system = build_chat_request(profile("Qwen3.8-27B"), request(ChatMessage.user("u")))
    assert roles(no_system.body) == ["user"]
    merged = build_chat_request(
        profile("Qwen3.8-27B"),
        request(ChatMessage.system("a"), ChatMessage.user("u"), ChatMessage.system("b")),
    )
    assert roles(merged.body) == ["system", "user"]
    assert merged.body["messages"][0]["content"] == "a\n\nb"


def test_glm_sends_developer_messages_as_system_and_keeps_positions() -> None:
    built = build_chat_request(
        profile("GLM-5.3-Flash"),
        request(ChatMessage.user("u"), ChatMessage.developer("d"), ChatMessage.system("s")),
    )
    assert roles(built.body) == ["user", "system", "system"]
    assert "developer" not in roles(built.body)


def test_deepseek_keeps_developer_role_and_several_system_messages() -> None:
    built = build_chat_request(
        profile("DeepSeek-V4-Flash"),
        request(ChatMessage.system("a"), ChatMessage.user("u"), ChatMessage.developer("d")),
    )
    assert roles(built.body) == ["system", "user", "developer"]
    assert built.adjustments == ()


# --- reasoning_effort ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "effort"),
    [
        ("GLM-5.3-Flash", "xhigh"),  # documented 422
        ("GLM-5.3-Flash", "none"),  # not in the documented list
        ("Qwen3.8-27B", "high"),  # documented 400
        ("Qwen3.8-27B", "none"),
        ("Qwen3.8-Flash-Next", "high"),
        ("Qwen3.8-Flash-Next", "minimal"),
        ("MiMo-V2.6-Flash", "max"),  # conservative reading of "the usual tiers"
        ("Gemma-4-31B-IT", "low"),  # on/off only; the "on" value is undocumented
    ],
)
def test_an_effort_outside_the_profile_is_refused_before_sending(model: str, effort: str) -> None:
    with pytest.raises(ProfileViolationError) as caught:
        build_chat_request(
            profile(model),
            request(ChatMessage.system("s"), ChatMessage.user("u"), reasoning_effort=effort),
        )
    assert caught.value.rule == "reasoning_effort"
    assert effort in caught.value.detail


@pytest.mark.parametrize(
    ("model", "effort"),
    [
        ("GLM-5.3-Flash", "low"),
        ("Qwen3.8-27B", "xhigh"),
        ("Qwen3.8-Flash-Next", "none"),
        ("MiMo-V2.6-Flash", "none"),
        ("DeepSeek-V4-Flash", "max"),
        ("Gemma-4-31B-IT", "none"),
    ],
)
def test_an_accepted_effort_is_sent_as_reasoning_effort(model: str, effort: str) -> None:
    built = build_chat_request(
        profile(model),
        request(ChatMessage.system("s"), ChatMessage.user("u"), reasoning_effort=effort),
    )
    assert built.body["reasoning_effort"] == effort
    assert "reasoning" not in built.body
    assert "thinking" not in built.body


def test_minicpm_takes_no_reasoning_effort_at_all() -> None:
    with pytest.raises(ProfileViolationError):
        build_chat_request(
            profile("MiniCPM5-2B"), request(ChatMessage.user("u"), reasoning_effort="low")
        )
    built = build_chat_request(profile("MiniCPM5-2B"), request(ChatMessage.user("u")))
    assert "reasoning_effort" not in built.body


def test_unknown_models_accept_only_low_and_medium() -> None:
    unknown = conservative_profile("MiniCPM-V-4.7-1B", None)
    for effort in ("low", "medium"):
        body = build_chat_request(
            unknown, request(ChatMessage.user("u"), reasoning_effort=effort)
        ).body
        assert body["reasoning_effort"] == effort
    for effort in ("none", "high", "xhigh"):
        with pytest.raises(ProfileViolationError):
            build_chat_request(unknown, request(ChatMessage.user("u"), reasoning_effort=effort))


# --- images -------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["GLM-5.3-Flash", "DeepSeek-V4-Flash", "MiniCPM5-2B"])
def test_images_are_stripped_for_text_only_models(model: str) -> None:
    built = build_chat_request(
        profile(model),
        request(ChatMessage.user([TextPart(text="look"), IMAGE, IMAGE])),
    )
    assert built.stripped_images == 2
    assert built.body["messages"][0]["content"] == f"look\n\n{IMAGE_REMOVED_NOTE}"
    assert "image_url" not in str(built.body)
    assert any("stripped 2 image" in note for note in built.adjustments)


@pytest.mark.parametrize(
    "model", ["DeepSeek-V4.1-Flash", "Qwen3.8-Flash-Next", "MiMo-V2.6-Flash", "Qwen3.8-27B"]
)
def test_images_are_kept_for_models_that_accept_them(model: str) -> None:
    built = build_chat_request(
        profile(model),
        request(ChatMessage.system("s"), ChatMessage.user([TextPart(text="look"), IMAGE])),
    )
    assert built.stripped_images == 0
    content = built.body["messages"][-1]["content"]
    assert content[1] == {"type": "image_url", "image_url": {"url": IMAGE.image_url.url}}


def test_text_only_part_lists_are_sent_as_plain_strings() -> None:
    built = build_chat_request(
        profile("DeepSeek-V4-Flash"),
        request(ChatMessage.user([TextPart(text="a"), TextPart(text="b")])),
    )
    assert built.body["messages"][0]["content"] == "a\n\nb"


def test_system_messages_cannot_carry_images() -> None:
    with pytest.raises(ValidationError):
        ChatMessage(role="system", content=[IMAGE])


# --- response formats, tools, parameters ------------------------------------------------------


def test_strict_json_schema_is_sent_only_to_a_model_that_accepts_it() -> None:
    fmt = ResponseFormat.strict_schema("report", {"type": "object", "properties": {}})
    # No documented model accepts it live (MiMo refused it, 2026-10-14); a hypothetical one.
    capable = profile("MiMo-V2.6-Flash").model_copy(update={"supports_json_schema": True})
    built = build_chat_request(
        capable, request(ChatMessage.user("JSON please"), response_format=fmt)
    )
    assert built.body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "report",
            "schema": {"type": "object", "properties": {}},
            "strict": True,
        },
    }
    for model in ("MiMo-V2.6-Flash", "GLM-5.3-Flash", "Qwen3.8-27B", "DeepSeek-V4-Flash"):
        with pytest.raises(ProfileViolationError) as caught:
            build_chat_request(
                profile(model), request(ChatMessage.user("JSON"), response_format=fmt)
            )
        assert caught.value.rule == "json_schema"


def test_json_object_is_accepted_by_every_chat_model() -> None:
    for model, prof in DOCUMENTED_PROFILES.items():
        if not prof.is_chat:
            continue
        built = build_chat_request(
            prof,
            request(
                ChatMessage.system("Answer in JSON."),
                ChatMessage.user("u"),
                response_format=ResponseFormat.json_object(),
            ),
        )
        assert built.body["response_format"] == {"type": "json_object"}, model


def test_text_response_format_is_omitted() -> None:
    built = build_chat_request(
        profile("DeepSeek-V4-Flash"),
        request(ChatMessage.user("u"), response_format=ResponseFormat(type="text")),
    )
    assert "response_format" not in built.body


def test_tools_tool_choice_and_parallel_flag_are_forwarded() -> None:
    built = build_chat_request(
        profile("DeepSeek-V4.1-Flash"),
        request(
            ChatMessage.user("u"),
            tools=(TOOL,),
            tool_choice=NamedToolChoice(function=NamedFunction(name="get_risk")),
            parallel_tool_calls=False,
        ),
    )
    assert built.body["tools"][0]["function"]["name"] == "get_risk"
    assert built.body["tool_choice"] == {"type": "function", "function": {"name": "get_risk"}}
    assert built.body["parallel_tool_calls"] is False


def test_only_accepted_parameters_are_emitted_and_never_stream_options() -> None:
    built = build_chat_request(
        profile("DeepSeek-V4-Flash"),
        request(
            ChatMessage.user("u"),
            temperature=0.2,
            top_p=0.9,
            presence_penalty=0.1,
            frequency_penalty=-0.1,
        ),
        stream=True,
    )
    assert set(built.body) == {
        "model",
        "messages",
        "max_tokens",
        "temperature",
        "top_p",
        "presence_penalty",
        "frequency_penalty",
        "stream",
    }
    assert built.body["stream"] is True
    not_streamed = build_chat_request(profile("DeepSeek-V4-Flash"), request(ChatMessage.user("u")))
    assert "stream" not in not_streamed.body


def test_max_tokens_beyond_the_context_window_is_refused() -> None:
    with pytest.raises(ProfileViolationError) as caught:
        build_chat_request(
            profile("Qwen3.8-27B"), request(ChatMessage.user("u"), max_tokens=131_073)
        )
    assert caught.value.rule == "max_tokens"


def test_the_ocr_model_cannot_serve_a_chat_request() -> None:
    with pytest.raises(ProfileViolationError) as caught:
        build_chat_request(profile("MinerU2.5-Pro"), request(ChatMessage.user("u")))
    assert caught.value.rule == "kind"


def test_request_level_validation() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(messages=(ChatMessage.user("u"),), max_tokens=0)
    with pytest.raises(ValidationError):
        ChatRequest(messages=(), max_tokens=10)
    with pytest.raises(ValidationError):
        ChatRequest(messages=(ChatMessage.user("u"),), max_tokens=10, tool_choice="auto")
    with pytest.raises(ValidationError):
        ChatRequest(
            messages=(ChatMessage.user("u"),),
            max_tokens=10,
            tools=(TOOL,),
            tool_choice=NamedToolChoice(function=NamedFunction(name="other")),
        )
    with pytest.raises(ValidationError):
        ChatRequest(messages=(ChatMessage.user("u"),), max_tokens=10, tools=(TOOL, TOOL))
    with pytest.raises(ValidationError):
        ChatRequest(messages=(ChatMessage.user("u"),), max_tokens=10, temperature=2.5)


# --- tool messages ------------------------------------------------------------------------------

CALL = ToolCall(id="call_1", function=FunctionCall(name="get_risk", arguments='{"unit_id": 1}'))


def test_tool_results_must_answer_the_preceding_tool_calls() -> None:
    good = build_chat_request(
        profile("DeepSeek-V4-Flash"),
        request(
            ChatMessage.user("u"),
            ChatMessage.assistant(tool_calls=(CALL,)),
            ChatMessage.tool("call_1", '{"risk": 0.5}'),
        ),
    )
    assert good.body["messages"][1]["tool_calls"][0]["id"] == "call_1"
    assert good.body["messages"][2] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"risk": 0.5}',
    }
    with pytest.raises(ProfileViolationError):
        build_chat_request(
            profile("DeepSeek-V4-Flash"),
            request(ChatMessage.user("u"), ChatMessage.tool("call_9", "{}")),
        )
    with pytest.raises(ProfileViolationError):
        build_chat_request(
            profile("DeepSeek-V4-Flash"),
            request(
                ChatMessage.user("u"),
                ChatMessage.assistant(tool_calls=(CALL,)),
                ChatMessage.user("next question before the tool answered"),
            ),
        )
    with pytest.raises(ProfileViolationError):
        build_chat_request(
            profile("DeepSeek-V4-Flash"),
            request(
                ChatMessage.user("u"),
                ChatMessage.assistant(tool_calls=(CALL, CALL)),
                ChatMessage.tool("call_1", "{}"),
            ),
        )


def test_message_shape_validation() -> None:
    with pytest.raises(ValidationError):
        ChatMessage(role="tool", content="x")
    with pytest.raises(ValidationError):
        ChatMessage(role="user", content="x", tool_call_id="call_1")
    with pytest.raises(ValidationError):
        ChatMessage(role="user", content="x", tool_calls=(CALL,))
    with pytest.raises(ValidationError):
        ChatMessage(role="assistant")
    with pytest.raises(ValidationError):
        ChatMessage(role="user")
