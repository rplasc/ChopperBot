from src.utils.websearch_util import (
    _normalize_results,
    format_results_for_prompt,
    sanitize_search_query,
    should_trigger_web_search,
)


def test_sanitize_strips_discord_artifacts():
    raw = "raul: <@123456> what's the latest on <#987654> <a:pog:11111> python 3.14?"
    cleaned = sanitize_search_query(raw)
    assert "<@" not in cleaned and "<#" not in cleaned and ":pog:" not in cleaned
    assert "python 3.14" in cleaned


def test_sanitize_caps_length():
    assert len(sanitize_search_query("word " * 100)) <= 200


def test_trigger_on_explicit_intent():
    assert should_trigger_web_search("can you look up the new Zelda game")
    assert should_trigger_web_search("what's the latest news?")


def test_trigger_on_time_sensitive_question():
    assert should_trigger_web_search("who won the game today?")
    assert should_trigger_web_search("what is the price of bitcoin right now?")


def test_no_trigger_on_casual_chat():
    assert not should_trigger_web_search("lol that was funny")
    assert not should_trigger_web_search("what is your favorite color?")


def test_normalize_results_shapes():
    rows = [{"title": "a"}, "junk", {"title": "b"}]
    assert _normalize_results(rows) == [{"title": "a"}, {"title": "b"}]
    assert _normalize_results({"results": rows}) == [{"title": "a"}, {"title": "b"}]
    assert _normalize_results("garbage") == []
    assert _normalize_results(None) == []


def test_format_results_skips_empty_and_truncates():
    results = [
        {"title": "First", "desc": "short desc", "url": "http://a"},
        {"title": "", "desc": ""},  # skipped
        {"title": "Long", "content": "word " * 200},
        {"title": "Alt snippet", "snippet": "from snippet key"},
    ]
    out = format_results_for_prompt(results)
    assert "1. First" in out and "http://a" in out
    assert "2. Long" in out and "…" in out
    assert "3. Alt snippet" in out and "from snippet key" in out


def test_format_results_respects_max():
    results = [{"title": f"t{i}", "desc": "d"} for i in range(10)]
    out = format_results_for_prompt(results, max_results=2)
    assert "t1" in out and "t2" not in out
