from meister_guide.ai.ranking import noise_penalty


def test_real_article_titles_score_zero():
    for title in ["Creeper", "Nether", "Crafting Table", "Elytra", "Redstone"]:
        assert noise_penalty(title) == 0.0


def test_disambiguation_is_penalised_hardest():
    assert noise_penalty("Creeper (disambiguation)") > noise_penalty("Bedrock Edition 1.16.0")


def test_version_and_changelog_pages_penalised():
    assert noise_penalty("Bedrock Edition 1.16.0") > 0
    assert noise_penalty("Bedrock Edition beta 1.16.0.57") > 0
    assert noise_penalty("Java Edition 1.20") > 0
    assert noise_penalty("Bedrock Edition 1.2.0/Development versions") > 0


def test_history_and_movie_pages_penalised():
    assert noise_penalty("Bedrock Edition mob render history") > 0
    assert noise_penalty("A Minecraft Movie") > 0
    assert noise_penalty("A Minecraft Movie Live Event") > 0
