import pytest
from meister_guide.ai.ollama_client import OllamaClient, OllamaUnavailable, pick_model


def test_list_models_parses_tags():
    def fake_get(url):
        assert url.endswith("/api/tags")
        return {"models": [{"name": "llama3:latest"}, {"name": "mistral"}]}
    client = OllamaClient(http_get=fake_get)
    assert client.list_models() == ["llama3:latest", "mistral"]


def test_list_models_raises_when_unreachable():
    def boom(url):
        raise OllamaUnavailable("connection refused")
    client = OllamaClient(http_get=boom)
    with pytest.raises(OllamaUnavailable):
        client.list_models()


def test_pick_model_prefers_llama3_then_first_then_none():
    assert pick_model(["mistral", "llama3:latest"]) == "llama3:latest"
    assert pick_model(["mistral", "phi"]) == "mistral"
    assert pick_model([]) is None


def test_chat_streams_content_chunks_until_done():
    sent = {}
    def fake_post(url, payload):
        sent["url"] = url
        sent["payload"] = payload
        return [
            '{"message": {"role": "assistant", "content": "Hel"}, "done": false}',
            '{"message": {"role": "assistant", "content": "lo"}, "done": false}',
            '',  # keep-alive / blank line, must be skipped
            '{"message": {"role": "assistant", "content": "!"}, "done": true}',
            '{"message": {"role": "assistant", "content": "IGNORED"}, "done": false}',
        ]
    client = OllamaClient(http_post=fake_post)
    chunks = list(client.chat("llama3", [{"role": "user", "content": "hi"}]))
    assert "".join(chunks) == "Hello!"        # stops at done, ignores trailing
    assert sent["url"].endswith("/api/chat")
    assert sent["payload"]["model"] == "llama3"
    assert sent["payload"]["stream"] is True


def test_chat_accepts_bytes_lines():
    def fake_post(url, payload):
        return [b'{"message": {"content": "hi"}, "done": true}']
    client = OllamaClient(http_post=fake_post)
    assert list(client.chat("m", [])) == ["hi"]


def test_chat_skips_whitespace_only_keepalive_lines():
    def fake_post(url, payload):
        return [
            "   ",   # whitespace-only keep-alive — must be skipped, not parsed
            '{"message": {"content": "ok"}, "done": true}',
        ]
    client = OllamaClient(http_post=fake_post)
    assert list(client.chat("m", [])) == ["ok"]   # no JSONDecodeError
