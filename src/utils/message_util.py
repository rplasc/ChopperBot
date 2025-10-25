from io import StringIO
from discord import File

DISCORD_MESSAGE_LIMIT = 2000
MAX_CHUNKS_BEFORE_FILE = 3

def chunk_message(content: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    if len(content) <= limit:
        return [content]

    chunks = []
    while len(content) > limit:
        split_at = content.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(content[:split_at])
        content = content[split_at:].lstrip()
    if content:
        chunks.append(content)
    return chunks

def to_discord_output(content: str):
    chunks = chunk_message(content)
    if len(chunks) > MAX_CHUNKS_BEFORE_FILE:
        fp = StringIO(content)
        return File(fp, filename="response.txt")
    return chunks