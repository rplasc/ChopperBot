try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
except ImportError:
    _enc = None

def count_tokens(text: str) -> int:
    if _enc:
        return len(_enc.encode(text))
    return len(text.split())

def trim_history(history, max_tokens: int = 2000):
    tokens_used = 0
    trimmed = []

    # Walk backwards through history until we run out of budget
    for entry in reversed(history):
        entry_text = entry.get("content", "")
        entry_tokens = count_tokens(entry_text)
        if tokens_used + entry_tokens > max_tokens:
            break
        trimmed.insert(0, entry)
        tokens_used += entry_tokens

    return trimmed