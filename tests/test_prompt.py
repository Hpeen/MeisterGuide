from meister_guide.ai.prompt import build_messages


def test_build_messages_structures_system_history_user():
    passages = [("Creeper", "A creeper explodes."), ("TNT", "TNT is craftable.")]
    history = [("user", "hi"), ("assistant", "hello")]
    msgs = build_messages("How do creepers work?", passages, history)

    assert msgs[0]["role"] == "system"
    assert "Creeper" in msgs[0]["content"] and "A creeper explodes." in msgs[0]["content"]
    assert "TNT" in msgs[0]["content"]
    assert msgs[1:3] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    assert msgs[-1] == {"role": "user", "content": "How do creepers work?"}


def test_build_messages_without_passages_has_no_excerpt_block():
    msgs = build_messages("hello", [], [])
    assert msgs[0]["role"] == "system"
    assert "Guide excerpts" not in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "hello"}
