"""Client for the Anthropic Claude API, exposing the same streaming
`chat(model, messages)` interface as OllamaClient so ChatStreamWorker stays
backend-agnostic. The SDK call is injected (`stream_factory`) so tests need
neither the `anthropic` package nor a network; the default factory lazy-imports
the SDK, so the app still runs fully offline when this backend isn't selected."""

DEFAULT_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 4096

# Offered in the settings model picker. Kept small and current rather than
# queried live, so the picker works before a key is even entered.
AVAILABLE_MODELS = ("claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5")


class ClaudeUnavailable(Exception):
    """The Claude API couldn't be used: no key, the `anthropic` package isn't
    installed, or the request was rejected (auth/rate limit/network). Mirrors
    OllamaUnavailable so the UI surfaces backend failures the same way."""


class ClaudeClient:
    def __init__(self, api_key, stream_factory=None, max_tokens=_MAX_TOKENS):
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._stream_factory = stream_factory or self._default_stream

    def chat(self, model, messages):
        """Stream a chat completion as text chunks. `messages` is the Ollama-style
        list (a leading 'system' turn plus user/assistant turns); it's converted
        to Anthropic's separate `system` string + role array."""
        system, converted = self._convert(messages)
        yield from self._stream_factory(model or DEFAULT_MODEL, system, converted)

    @staticmethod
    def _convert(messages):
        """Split Ollama-style messages into (system_text, anthropic_messages).
        Anthropic takes the system prompt as a separate argument and rejects a
        'system' role inside the messages array, so system turns are pulled out
        and concatenated; the rest keep their role and order."""
        system_parts, converted = [], []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                converted.append({"role": role, "content": content})
        return "\n\n".join(system_parts), converted

    def _default_stream(self, model, system, messages):
        # Key check first so a missing key fails the same way whether or not the
        # SDK is installed.
        if not self._api_key:
            raise ClaudeUnavailable("No Claude API key set.")
        try:
            import anthropic
        except ImportError as err:
            raise ClaudeUnavailable(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            ) from err
        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            kwargs = {"model": model, "max_tokens": self._max_tokens,
                      "messages": messages}
            if system:
                kwargs["system"] = system
            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield text
        except anthropic.APIError as err:   # auth, rate limit, overloaded, etc.
            raise ClaudeUnavailable(str(err)) from err
