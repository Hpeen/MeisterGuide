import pytest
from meister_guide.ai.claude_client import (
    ClaudeClient, ClaudeUnavailable, DEFAULT_MODEL,
)


def test_convert_splits_system_out_of_messages():
    system, msgs = ClaudeClient._convert([
        {"role": "system", "content": "preamble"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "bye"},
    ])
    assert system == "preamble"
    assert msgs == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "bye"},
    ]


def test_convert_concatenates_multiple_system_turns():
    system, msgs = ClaudeClient._convert([
        {"role": "system", "content": "a"},
        {"role": "system", "content": "b"},
        {"role": "user", "content": "q"},
    ])
    assert system == "a\n\nb"
    assert msgs == [{"role": "user", "content": "q"}]


def test_chat_streams_chunks_through_factory():
    captured = {}
    def fake_factory(model, system, messages):
        captured["model"] = model
        captured["system"] = system
        captured["messages"] = messages
        yield "Cree"
        yield "pers "
        yield "explode."
    client = ClaudeClient(api_key="k", stream_factory=fake_factory)
    out = "".join(client.chat("claude-opus-4-8", [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "what is a creeper"},
    ]))
    assert out == "Creepers explode."
    assert captured["model"] == "claude-opus-4-8"
    assert captured["system"] == "sys"
    assert captured["messages"] == [{"role": "user", "content": "what is a creeper"}]


def test_chat_falls_back_to_default_model_when_none():
    seen = {}
    def fake_factory(model, system, messages):
        seen["model"] = model
        yield "x"
    list(ClaudeClient(api_key="k", stream_factory=fake_factory).chat(None, []))
    assert seen["model"] == DEFAULT_MODEL


def test_default_stream_without_key_raises_unavailable():
    # No key set: must fail with ClaudeUnavailable (deterministic — the key check
    # runs before the optional SDK import).
    client = ClaudeClient(api_key="")
    with pytest.raises(ClaudeUnavailable):
        list(client.chat(DEFAULT_MODEL, [{"role": "user", "content": "hi"}]))
