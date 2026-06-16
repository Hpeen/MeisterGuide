"""Build the Ollama /api/chat `messages` array: a system prompt carrying the
retrieved guide excerpts, the prior turns, then the new question."""

SYSTEM_PREAMBLE = (
    "You are Meister, a helpful in-game Minecraft assistant. Answer the user's "
    "question using the guide excerpts below when they are relevant. If the "
    "excerpts do not contain the answer, say you are not sure based on the "
    "available guides rather than inventing details. Keep answers concise."
)


def build_messages(question, passages, history):
    """passages: list[(title, text)]; history: list[(role, content)]."""
    system = SYSTEM_PREAMBLE
    if passages:
        blocks = "\n\n".join(f"[{title}]\n{text}" for title, text in passages)
        system += "\n\n--- Guide excerpts ---\n" + blocks + "\n--- end excerpts ---"
    messages = [{"role": "system", "content": system}]
    for role, content in history:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    return messages
