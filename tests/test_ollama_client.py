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
