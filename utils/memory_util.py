import difflib

def significant_change(old: str, new: str, threshold: float = 0.65) -> bool:
    ratio = difflib.SequenceMatcher(None, old, new).ratio()
    return ratio < threshold
