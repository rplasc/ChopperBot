from src.services.personality_engine import (
    TRAITS,
    DEFAULT_SCORE,
    apply_deltas,
    clamp_score,
    derive_archetype,
    parse_trait_deltas,
    summarize_traits,
)


def _neutral():
    return {t: DEFAULT_SCORE for t in TRAITS}


def test_clamp_score_bounds():
    assert clamp_score(-5) == 0.0
    assert clamp_score(150) == 100.0
    assert clamp_score(42.5) == 42.5


def test_parse_trait_deltas_formats():
    deltas = parse_trait_deltas("curiosity +2\nHumor: -1\nlogic = +3")
    assert deltas == {"curiosity": 2.0, "humor": -1.0, "logic": 3.0}


def test_parse_trait_deltas_clamps_and_ignores_unknown():
    deltas = parse_trait_deltas("curiosity +30\nswagger +2\nnone")
    assert deltas == {"curiosity": 3.0}


def test_apply_deltas_clamps_scores():
    traits = _neutral()
    traits["confidence"] = 99.0
    updated = apply_deltas(traits, {"confidence": 3.0, "humor": -2.0})
    assert updated["confidence"] == 100.0
    assert updated["humor"] == 48.0
    # untouched traits stay put
    assert updated["logic"] == DEFAULT_SCORE


def test_neutral_profile_is_balanced():
    name, _ = derive_archetype(_neutral())
    assert name == "Balanced"
    assert derive_archetype({})[0] == "Balanced"


def test_archetype_matches_dominant_traits():
    traits = _neutral()
    traits["humor"] = 80.0
    traits["creativity"] = 70.0
    assert derive_archetype(traits)[0] == "Trickster"

    traits = _neutral()
    traits["logic"] = 85.0
    traits["curiosity"] = 80.0
    assert derive_archetype(traits)[0] == "Scholar"


def test_summarize_traits():
    assert summarize_traits(_neutral()) == ""

    traits = _neutral()
    traits["curiosity"] = 75.0
    traits["kindness"] = 40.0
    summary = summarize_traits(traits)
    assert "high curiosity" in summary
    assert "low kindness" in summary
    assert "archetype:" in summary
