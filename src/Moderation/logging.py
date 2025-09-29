import logging
from logging.handlers import RotatingFileHandler
import aiosqlite
import datetime
import os

# === File Logging Setup ===
LOG_DIR = "data/logs"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("chopperbot")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "bot.log"),
    maxBytes=5_000_000,  # 5 MB per file
    backupCount=5        # keep last 5 logs
)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


# === Chat Log Database Setup ===
DB_PATH = "data/analytics.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


async def init_logging_db():
    """Initialize the chat log DB if not exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id TEXT,
                channel_id TEXT,
                user_id TEXT,
                username TEXT,
                role TEXT, -- 'user' or 'assistant'
                content TEXT,
                timestamp TEXT
            )
        """)
        await db.commit()


async def log_chat_message(server_id: str, channel_id: str, user_id: str,
                           username: str, role: str, content: str):
    """Store a chat message in the DB for analytics."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO chat_logs (server_id, channel_id, user_id, username, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (server_id, channel_id, user_id, username, role, content, timestamp))
        await db.commit()