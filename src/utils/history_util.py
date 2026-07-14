def count_tokens(text: str) -> int:
    # Rough estimate (~4 chars/token for English); good enough for trimming
    # history to a budget without pulling in a tokenizer dependency.
    return max(1, len(text) // 4)

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
