from meister_guide.ai.query import clean_query


def test_strips_question_and_stop_words():
    assert clean_query("how do I make a nether portal?") == ["nether", "portal"]


def test_lowercases_and_drops_punctuation():
    assert clean_query("How do CREEPERS work??!") == ["creepers"]


def test_dedupes_preserving_order():
    assert clean_query("iron iron golem golem") == ["iron", "golem"]


def test_drops_one_char_tokens():
    assert clean_query("a b diamond") == ["diamond"]


def test_falls_back_to_raw_tokens_when_all_stopwords():
    # every token is a stop/short word -> don't return empty
    assert clean_query("how do you do") == ["how", "do", "you"]
