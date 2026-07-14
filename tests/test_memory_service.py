import datetime

from src.services.memory_service import (
    build_fts_query,
    clamp_importance,
    parse_fact_lines,
    rerank_memories,
)


def test_build_fts_query_uses_or_and_drops_stopwords():
    query = build_fts_query("do you like python bots?")
    assert query == "python OR bots"


def test_build_fts_query_dedupes_and_caps_terms():
    query = build_fts_query("code code code " + " ".join(f"word{i}" for i in range(20)))
    terms = query.split(" OR ")
    assert terms[0] == "code"
    assert len(terms) == 12
    assert len(set(terms)) == 12


def test_build_fts_query_empty_input():
    assert build_fts_query("") == ""
    assert build_fts_query("do you the a?!") == ""


def test_clamp_importance_bounds():
    assert clamp_importance(None) == 3
    assert clamp_importance(0) == 1
    assert clamp_importance(9) == 5
    assert clamp_importance(4) == 4


def test_parse_fact_lines_v2_format():
    raw = "[skill|4] Writes Python tooling\n[preference|2] Prefers dark mode"
    facts = parse_fact_lines(raw)
    assert facts == [
        {"category": "skill", "importance": 4, "content": "Writes Python tooling"},
        {"category": "preference", "importance": 2, "content": "Prefers dark mode"},
    ]


def test_parse_fact_lines_legacy_format():
    facts = parse_fact_lines("[trait] Is sarcastic")
    assert facts == [{"category": "trait", "importance": 3, "content": "Is sarcastic"}]


def test_parse_fact_lines_untagged_and_noise():
    facts = parse_fact_lines(
        "- Enjoys hiking on weekends\n"
        "Here are the facts:\n"
        "no changes\n"
        "\n"
    )
    assert len(facts) == 1
    assert facts[0]["category"] == "observation"
    assert facts[0]["content"] == "Enjoys hiking on weekends"


def test_parse_fact_lines_clamps_importance():
    facts = parse_fact_lines("[goal|9] Wants to run a marathon")
    assert facts[0]["importance"] == 5


def test_rerank_prefers_important_memories():
    now = datetime.datetime.now(datetime.timezone.utc)
    recent = now.isoformat()
    rows = [
        {"content": "trivial", "bm25": -1.0, "importance": 1, "created_at": recent},
        {"content": "defining", "bm25": -1.0, "importance": 5, "created_at": recent},
    ]
    ranked = rerank_memories(rows, limit=2, now=now)
    assert ranked[0]["content"] == "defining"


def test_rerank_prefers_recent_when_otherwise_equal():
    now = datetime.datetime.now(datetime.timezone.utc)
    old = (now - datetime.timedelta(days=365)).isoformat()
    rows = [
        {"content": "old", "bm25": -1.0, "importance": 3, "created_at": old},
        {"content": "new", "bm25": -1.0, "importance": 3, "created_at": now.isoformat()},
    ]
    ranked = rerank_memories(rows, limit=1, now=now)
    assert ranked[0]["content"] == "new"


def test_rerank_respects_limit_and_bad_dates():
    rows = [
        {"content": f"m{i}", "bm25": -float(i), "importance": 3, "created_at": "not-a-date"}
        for i in range(5)
    ]
    ranked = rerank_memories(rows, limit=3)
    assert len(ranked) == 3
    # bm25 more negative = more relevant
    assert ranked[0]["content"] == "m4"
