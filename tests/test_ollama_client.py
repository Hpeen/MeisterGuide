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


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines
        self.closed = False

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line

    def close(self):
        self.closed = True


def test_iter_close_releases_response_even_when_consumer_stops_early():
    resp = _FakeResponse(["a", "b", "c"])
    gen = OllamaClient._iter_close(resp)
    assert next(gen) == "a"     # consume one line, then abandon the stream
    gen.close()                 # mimic chat() breaking on `done` / cancel
    assert resp.closed is True


def test_default_post_surfaces_ollama_error_body(monkeypatch):
    import requests

    class _ErrResp:
        status_code = 500
        text = '{"error": "model requires more system memory"}'
        def close(self):
            pass

    monkeypatch.setattr(requests, "post", lambda *a, **k: _ErrResp())
    client = OllamaClient()  # real default path
    with pytest.raises(OllamaUnavailable) as ei:
        list(client.chat("llama3", [{"role": "user", "content": "hi"}]))
    assert "model requires more system memory" in str(ei.value)
    assert "500" in str(ei.value)


def test_chat_skips_whitespace_only_keepalive_lines():
    def fake_post(url, payload):
        return [
            "   ",   # whitespace-only keep-alive — must be skipped, not parsed
            '{"message": {"content": "ok"}, "done": true}',
        ]
    client = OllamaClient(http_post=fake_post)
    assert list(client.chat("m", [])) == ["ok"]   # no JSONDecodeError


# tests/test_ollama_client.py  (append)
from meister_guide.ai.ollama_client import pick_best_model


def _m(name, size=None, caps=None):
    d = {"name": name, "details": {}}
    if size is not None:
        d["details"]["parameter_size"] = size
    if caps is not None:
        d["capabilities"] = caps
    return d


def test_pick_best_model_prefers_largest_completion_model():
    models = [
        _m("llama3:latest", "8.0B", ["completion"]),
        _m("qwen2.5:32b", "32.8B", ["completion", "tools"]),
        _m("llama3.2:latest", "3.2B", ["completion", "tools"]),
    ]
    assert pick_best_model(models) == "qwen2.5:32b"


def test_pick_best_model_skips_embedding_only():
    models = [
        _m("nomic-embed-text", "0.1B", ["embedding"]),
        _m("llama3:latest", "8.0B", ["completion"]),
    ]
    assert pick_best_model(models) == "llama3:latest"


def test_pick_best_model_falls_back_to_name_pref_without_sizes():
    models = [_m("mistral"), _m("llama3:latest")]  # no parameter_size
    assert pick_best_model(models) == "llama3:latest"   # llama3 preference


def test_pick_best_model_none_when_empty():
    assert pick_best_model([]) is None


def test_pick_best_model_skips_subbillion_embedding_without_caps():
    # No capabilities field (older Ollama): a 137M embedding model must not
    # outrank an 8B chat model. Both the unit-aware size and the name guard
    # protect against this.
    models = [_m("llama3:latest", "8.0B"), _m("nomic-embed-text", "137M")]
    assert pick_best_model(models) == "llama3:latest"
