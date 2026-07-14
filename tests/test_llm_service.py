from src.services.llm_service import build_payload, resolve_config


def test_resolve_config_defaults_to_koboldcpp():
    config = resolve_config(env={})
    assert config["provider"] == "koboldcpp"
    assert config["url"] == "http://127.0.0.1:5001/v1/chat/completions"


def test_resolve_config_legacy_kobold_env():
    config = resolve_config(env={"KOBOLD_TEXT_API": "http://myhost:5001/v1/chat/completions"})
    assert config["url"] == "http://myhost:5001/v1/chat/completions"


def test_resolve_config_openai_falls_back_to_legacy_keys():
    config = resolve_config(env={
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test",
        "GPT_ENGINE": "gpt-4.1-nano",
    })
    assert config["provider"] == "openai"
    assert config["api_key"] == "sk-test"
    assert config["model"] == "gpt-4.1-nano"
    assert config["url"] == "https://api.openai.com/v1/chat/completions"


def test_resolve_config_unknown_provider_falls_back():
    config = resolve_config(env={"LLM_PROVIDER": "banana"})
    assert config["provider"] == "koboldcpp"


def test_resolve_config_explicit_url_wins():
    config = resolve_config(env={
        "LLM_PROVIDER": "ollama",
        "LLM_API_URL": "http://gpu-box:11434/v1/chat/completions",
    })
    assert config["url"] == "http://gpu-box:11434/v1/chat/completions"


def test_build_payload_merges_params():
    payload = build_payload(
        [{"role": "user", "content": "hi"}],
        {"temperature": 0.5, "max_tokens": 100},
    )
    assert payload["temperature"] == 0.5
    assert payload["max_tokens"] == 100
    assert payload["repetition_penalty"] == 1.15  # default preserved
    assert payload["messages"][0]["content"] == "hi"


def test_build_payload_filters_openai_params():
    payload = build_payload(
        [{"role": "user", "content": "hi"}],
        provider="openai",
        model="gpt-4.1-nano",
    )
    assert "repetition_penalty" not in payload
    assert "top_k" not in payload
    assert payload["model"] == "gpt-4.1-nano"


def test_build_payload_ignores_none_params():
    payload = build_payload([{"role": "user", "content": "hi"}], {"temperature": None})
    assert payload["temperature"] == 0.8
