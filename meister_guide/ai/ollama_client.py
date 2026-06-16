"""Client for a local Ollama server. HTTP is injectable so tests run without a
server; defaults use `requests`. Connection failures raise OllamaUnavailable."""
import json

DEFAULT_BASE = "http://localhost:11434"


class OllamaUnavailable(Exception):
    """Ollama could not be reached (not running / wrong port / network)."""


def pick_model(names):
    """Prefer a llama3* model, else the first installed, else None."""
    for name in names:
        if name.startswith("llama3"):
            return name
    return names[0] if names else None


class OllamaClient:
    def __init__(self, base_url=DEFAULT_BASE, http_get=None, http_post=None):
        self._base = base_url.rstrip("/")
        self._http_get = http_get or self._default_get
        self._http_post = http_post or self._default_post_lines

    def _default_get(self, url):
        import requests
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as err:
            raise OllamaUnavailable(str(err))

    def _default_post_lines(self, url, payload):
        import requests
        try:
            resp = requests.post(url, json=payload, stream=True, timeout=300)
            resp.raise_for_status()
            return resp.iter_lines(decode_unicode=True)
        except requests.RequestException as err:
            raise OllamaUnavailable(str(err))

    def list_models(self):
        data = self._http_get(self._base + "/api/tags")
        return [m["name"] for m in data.get("models", [])]

    def chat(self, model, messages):
        """Stream a chat completion, yielding content chunks. Stops at the line
        whose `done` is true. `_http_post` returns an iterable of NDJSON lines
        (str or bytes)."""
        lines = self._http_post(
            self._base + "/api/chat",
            {"model": model, "messages": messages, "stream": True},
        )
        for line in lines:
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            if not line or not line.strip():
                continue
            obj = json.loads(line)
            chunk = (obj.get("message") or {}).get("content", "")
            if chunk:
                yield chunk
            if obj.get("done"):
                break
