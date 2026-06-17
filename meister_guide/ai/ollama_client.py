"""Client for a local Ollama server. HTTP is injectable so tests run without a
server; defaults use `requests`. Connection failures raise OllamaUnavailable."""
import json
import re

DEFAULT_BASE = "http://localhost:11434"


class OllamaUnavailable(Exception):
    """Ollama could not be reached (not running / wrong port / network)."""


def pick_model(names):
    """Prefer a llama3* model, else the first installed, else None."""
    for name in names:
        if name.startswith("llama3"):
            return name
    return names[0] if names else None


def _parse_size(text):
    """Parameter count in billions: '32.8B' -> 32.8, '8.0B' -> 8.0, '7B' -> 7,
    '137M' -> 0.137, missing -> 0.0. The unit matters — an embedding model's
    '137M' must not outrank an '8.0B' chat model."""
    if not text:
        return 0.0
    m = re.match(r"([\d.]+)\s*([bmk]?)", str(text).strip().lower())
    if not m:
        return 0.0
    value = float(m.group(1))
    scale = {"b": 1.0, "m": 1e-3, "k": 1e-6, "": 1.0}[m.group(2)]
    return value * scale


# Models that can't actually hold a chat, even if they don't advertise their
# capabilities on older Ollama builds (the /api/tags capabilities field is new).
_NON_CHAT_HINTS = ("embed", "bge", "nomic", "minilm")


def pick_best_model(models):
    """`models`: raw /api/tags entries. Pick the largest completion-capable
    text model (so qwen2.5:32b beats llama3). Skip embedding-only / non-
    completion models. If no size info is available, fall back to the
    name-preference in pick_model."""
    eligible = []
    for m in models:
        name = m.get("name")
        if not name:
            continue
        caps = m.get("capabilities") or []
        if caps and "completion" not in caps:
            continue
        if not caps and any(h in name.lower() for h in _NON_CHAT_HINTS):
            continue  # no capabilities field — guard known embedding models by name
        size = _parse_size((m.get("details") or {}).get("parameter_size"))
        eligible.append((size, name))
    if not eligible:
        return None
    if all(size == 0.0 for size, _ in eligible):
        return pick_model([name for _, name in eligible])
    eligible.sort(key=lambda pair: pair[0], reverse=True)
    return eligible[0][1]


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
        except requests.RequestException as err:
            raise OllamaUnavailable(str(err))
        if resp.status_code >= 400:
            # Ollama returns the real reason in the body ({"error": "..."}),
            # e.g. "model requires more system memory" — surface it instead of
            # the opaque "500 Server Error" raise_for_status() would give.
            detail = (resp.text or "").strip()
            resp.close()
            try:
                detail = json.loads(detail).get("error", detail)
            except (ValueError, TypeError):
                pass
            raise OllamaUnavailable(
                f"Ollama returned {resp.status_code}: {detail or 'no detail'}")
        return self._iter_close(resp)

    @staticmethod
    def _iter_close(resp):
        """Yield NDJSON lines, then release the connection — even if the caller
        stops early (done flag, cancel) and the body is only partly read."""
        try:
            for line in resp.iter_lines(decode_unicode=True):
                yield line
        finally:
            resp.close()

    def list_models(self):
        data = self._http_get(self._base + "/api/tags")
        return [m["name"] for m in data.get("models", [])]

    def list_model_info(self):
        """Raw /api/tags model entries (name + details + capabilities)."""
        data = self._http_get(self._base + "/api/tags")
        return data.get("models", [])

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
