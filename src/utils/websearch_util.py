import asyncio
import re
import aiohttp
from src.moderation.logging import logger
from src.aclient import client

# Detect your KoboldCPP endpoint
WEBSEARCH_API_URL = client.kobold_web_api

SEARCH_TIMEOUT_SECONDS = 15
SEARCH_MAX_RETRIES = 2
MAX_QUERY_LENGTH = 200
MAX_RESULTS = 5
MAX_SNIPPET_LENGTH = 500

# ============================================================================
# QUERY PREPARATION & TRIGGERING
# ============================================================================

def sanitize_search_query(content: str) -> str:
    """Strip Discord artifacts from a message so it works as a search query."""
    # Remove username prefix pattern: "username: message"
    content = re.sub(r'^[\w\s]+:\s*', '', content)

    # Remove user/role/channel mentions and custom emoji
    content = re.sub(r'<@!?\d+>', '', content)
    content = re.sub(r'<@&\d+>', '', content)
    content = re.sub(r'<#\d+>', '', content)
    content = re.sub(r'<a?:\w+:\d+>', '', content)

    # Collapse whitespace and cap length (long messages make bad queries)
    content = re.sub(r'\s+', ' ', content).strip()
    return content[:MAX_QUERY_LENGTH].strip()

def should_trigger_web_search(content: str) -> bool:
    """Heuristic for when a message needs fresh information from the web."""
    content_lower = content.lower()

    # 1. Explicit search intent
    explicit_search_terms = [
        "search for", "look up", "look it up", "find information about",
        "google", "what's happening", "latest news", "recent news",
        "current events", "breaking news",
    ]
    if any(term in content_lower for term in explicit_search_terms):
        return True

    # 2. Time-sensitive indicators
    time_indicators = [
        "today", "tonight", "yesterday", "this week", "this month",
        "right now", "currently", "recent", "latest", "upcoming",
    ]

    # 3. Date references (current-era years, month names)
    date_pattern = r'\b(202[4-9]|january|february|march|april|may|june|july|august|september|october|november|december)\b'
    has_date = bool(re.search(date_pattern, content_lower))

    # 4. Current-event topics (sports scores, elections, prices, releases)
    current_event_keywords = [
        "score", "election", "weather forecast", "stock price", "price of",
        "who won", "who's winning", "game result", "release date",
    ]

    is_question = "?" in content or any(
        q in content_lower for q in ["what", "who", "when", "how"]
    )
    has_time_signal = any(indicator in content_lower for indicator in time_indicators)
    has_current_topic = any(keyword in content_lower for keyword in current_event_keywords)

    if is_question and (has_date or has_current_topic):
        return True

    if is_question and has_time_signal and len(content.split()) >= 4:
        return True

    return False

# ============================================================================
# SEARCH EXECUTION
# ============================================================================

def _normalize_results(data) -> list:
    """Accept the shapes different search backends return and normalize to a
    list of result dicts. Returns [] for anything unusable."""
    if isinstance(data, dict):
        # Some endpoints wrap results: {"results": [...]}
        data = data.get("results", [])
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]

async def perform_web_search(query: str) -> list:
    """Run a web search with timeout and retries.

    Never raises — returns [] when the endpoint is unconfigured, unreachable,
    or returns garbage, so callers degrade gracefully to a no-search answer.
    """
    if not WEBSEARCH_API_URL:
        logger.debug("WebSearch skipped: no endpoint configured")
        return []

    query = query.strip()
    if not query:
        return []

    payload = {"q": query}
    last_error = None

    for attempt in range(SEARCH_MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    WEBSEARCH_API_URL, json=payload,
                    timeout=aiohttp.ClientTimeout(total=SEARCH_TIMEOUT_SECONDS)
                ) as resp:
                    if resp.status != 200:
                        last_error = f"HTTP {resp.status}: {(await resp.text())[:200]}"
                    else:
                        results = _normalize_results(await resp.json())
                        if results:
                            logger.info(f"WebSearch fetched {len(results)} results for '{query}'")
                            return results
                        last_error = "empty or malformed result set"
        except asyncio.TimeoutError:
            last_error = f"timeout after {SEARCH_TIMEOUT_SECONDS}s"
        except Exception as e:
            last_error = str(e)

        if attempt < SEARCH_MAX_RETRIES:
            await asyncio.sleep(1.5 * (attempt + 1))

    logger.warning(f"WebSearch failed for '{query}' after {SEARCH_MAX_RETRIES + 1} attempts: {last_error}")
    return []

def format_results_for_prompt(results: list, max_results: int = MAX_RESULTS) -> str:
    """Render results for prompt injection; skips empty rows and caps snippet
    length so search output can't blow the context budget."""
    formatted = []
    for r in results[:max_results]:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        snippet = (r.get("desc") or r.get("content") or r.get("snippet") or "").strip()
        if not snippet and not title:
            continue
        title = title or "Untitled"
        if len(snippet) > MAX_SNIPPET_LENGTH:
            snippet = snippet[:MAX_SNIPPET_LENGTH].rsplit(" ", 1)[0] + "…"
        entry = f"{len(formatted) + 1}. {title}"
        if snippet:
            entry += f"\n{snippet}"
        if url:
            entry += f"\n({url})"
        formatted.append(entry)
    return "\n\n".join(formatted)
