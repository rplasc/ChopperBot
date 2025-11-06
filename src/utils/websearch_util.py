import aiohttp
from src.moderation.logging import logger
from src.aclient import client

# Detect your KoboldCPP endpoint
WEBSEARCH_API_URL = client.kobold_web_api

async def perform_web_search(query: str) -> list:

    payload = {
        "q": query,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(WEBSEARCH_API_URL, json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"WebSearch error {resp.status}: {error_text}")
            data = await resp.json()
            logger.info(f"WebSearch fetched {len(data)} results for '{query}'")
            return data

def format_results_for_prompt(results: list) -> str:

    formatted = []
    for i, r in enumerate(results[:5], start=1):
        title = r.get("title", "Untitled")
        snippet = r.get("snippet", "")
        url = r.get("url", "")
        formatted.append(f"{i}. {title}\n{snippet}\n({url})\n")
    return "\n".join(formatted)
