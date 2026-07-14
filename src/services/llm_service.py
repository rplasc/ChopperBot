"""Provider-agnostic LLM service.

Every text-generation call in the bot goes through this module so that
switching between KoboldCPP, Ollama, LM Studio, or OpenAI only requires
configuration changes (env vars), not code changes.

All supported providers speak the OpenAI-compatible
``/v1/chat/completions`` protocol; they differ only in default URL,
authentication, and which sampling parameters they accept.
"""

import os
import aiohttp
from typing import Dict, List, Optional

from src.moderation.logging import logger

# Default endpoint per provider when LLM_API_URL is not set
PROVIDER_DEFAULT_URLS = {
    "koboldcpp": "http://127.0.0.1:5001/v1/chat/completions",
    "ollama": "http://127.0.0.1:11434/v1/chat/completions",
    "lmstudio": "http://127.0.0.1:1234/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
}

# Parameters the OpenAI cloud API accepts; local providers accept extras
# like top_k / repetition_penalty and silently benefit from them.
OPENAI_SAFE_PARAMS = {
    "temperature", "top_p", "frequency_penalty", "presence_penalty",
    "max_tokens", "stop", "model",
}

DEFAULT_PARAMS = {
    "temperature": 0.8,
    "top_p": 0.9,
    "top_k": 50,
    "frequency_penalty": 1.0,
    "presence_penalty": 0.6,
    "repetition_penalty": 1.15,
    "max_tokens": 400,
    "stop": ["\nUser:", "\nSystem:", "\nAssistant:", "\n\n\n"],
}


def resolve_config(env: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
    """Resolve provider configuration from environment variables.

    Precedence for the URL: LLM_API_URL > legacy KOBOLD_TEXT_API /
    KOBOLD_API_URL (koboldcpp only) > provider default.
    """
    getenv = (env or os.environ).get
    provider = (getenv("LLM_PROVIDER") or "koboldcpp").strip().lower()
    if provider not in PROVIDER_DEFAULT_URLS:
        logger.warning(f"[LLM] Unknown provider '{provider}', falling back to koboldcpp")
        provider = "koboldcpp"

    url = getenv("LLM_API_URL")
    if not url and provider == "koboldcpp":
        url = getenv("KOBOLD_TEXT_API") or getenv("KOBOLD_API_URL")
    if not url:
        url = PROVIDER_DEFAULT_URLS[provider]

    api_key = getenv("LLM_API_KEY")
    if not api_key and provider == "openai":
        api_key = getenv("OPENAI_API_KEY")

    model = getenv("LLM_MODEL")
    if not model and provider == "openai":
        model = getenv("GPT_ENGINE")

    return {"provider": provider, "url": url, "api_key": api_key, "model": model}


def build_payload(
    messages: List[Dict],
    params: Optional[Dict] = None,
    provider: str = "koboldcpp",
    model: Optional[str] = None,
) -> Dict:
    """Merge defaults with per-call params and filter for the provider."""
    merged = dict(DEFAULT_PARAMS)
    if params:
        merged.update({k: v for k, v in params.items() if v is not None})
    if model:
        merged["model"] = model

    if provider == "openai":
        merged = {k: v for k, v in merged.items() if k in OPENAI_SAFE_PARAMS}

    merged["messages"] = messages
    return merged


class LLMService:
    def __init__(self, env: Optional[Dict[str, str]] = None):
        config = resolve_config(env)
        self.provider = config["provider"]
        self.url = config["url"]
        self.api_key = config["api_key"]
        self.model = config["model"]
        self.timeout = float(os.getenv("LLM_TIMEOUT", "60"))

    async def chat(self, messages: List[Dict], params: Optional[Dict] = None) -> str:
        """Send a chat-completion request and return the assistant text."""
        payload = build_payload(messages, params, self.provider, self.model)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"LLM API error {resp.status}: {error_text}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]


# Global instance used by the whole bot
llm_service = LLMService()


async def chat_completion(messages: List[Dict], params: Optional[Dict] = None) -> str:
    return await llm_service.chat(messages, params)
