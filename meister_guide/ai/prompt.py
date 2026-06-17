"""Build the Ollama /api/chat `messages` array: a system prompt carrying the
retrieved guide excerpts, the prior turns, then the new question."""

SYSTEM_PREAMBLE = (
    "You are Meister, a friendly in-game Minecraft assistant. Answer the "
    "player's question using the guide excerpts below as your source of truth. "
    "When the question is about how to do or craft something, give clear "
    "numbered steps. Be concise and specific — use the exact block, item, and "
    "amount names from the excerpts. If the excerpts do not contain the answer, "
    "say so plainly instead of guessing."
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
