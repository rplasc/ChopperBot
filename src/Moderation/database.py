import os
import aiosqlite
import asyncio
import datetime
from utils.kobaldcpp_util import get_kobold_response

DB_PATH =  "data/bot_data.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Initializes yaps and summary tables
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS yaps (
                server_id TEXT,
                user_id TEXT,
                count INTEGER,
                PRIMARY KEY (server_id, user_id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server_id ON yaps (server_id)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_logs (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                interactions INTEGER DEFAULT 0,
                last_seen TEXT,
                personality_notes TEXT
            )
        """)    
        await db.commit()

#---- Functions for 'yaps' ----#
write_queue = asyncio.Queue()
async def queue_increment(server_id: str, user_id: str):
    await write_queue.put((server_id, user_id))

async def increment_yap():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
             while True:
                server_id, user_id = await write_queue.get()
                await db.execute("""
                    INSERT INTO yaps (server_id, user_id, count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(server_id, user_id)
                    DO UPDATE SET count = count + 1
                """, (server_id, user_id))
                await db.commit()
                write_queue.task_done()
    except aiosqlite.Error as e:
        print(f"Database error in increment_yap: {e}")

async def show_yaps_user(server_id: str, user_id: str) -> int:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT count FROM yaps WHERE server_id=? AND user_id=?", (server_id, user_id))
            row = await cursor.fetchone()
            count = row[0] if row else 0
            return count
    except aiosqlite.Error as e:
        print(f"Database error in show_yaps_user: {e}")

async def show_yaps_leaderboard(server_id: str):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id, count FROM yaps WHERE server_id=? ORDER BY count DESC LIMIT 10",
                (server_id,)
            )
            top_users = await cursor.fetchall()        
            return top_users
    except aiosqlite.Error as e:
        print(f"Database error in show_yaps_leaderboard: {e}")

#---- Functions for User Logs ----#
user_log_queue = {}

async def queue_user_log(user_id: str, username: str, notes: str =None):
    record = user_log_queue.get(user_id, {
        "username": username,
        "interactions": 0,
        "last_seen": None
    })
    record["username"] = username
    record["interactions"] += 1
    record["last_seen"] = datetime.datetime.now(datetime.timezone.utc)
    user_log_queue[user_id] = record

async def flush_user_logs():
    if not user_log_queue:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        for uid, data in user_log_queue.items():
            await db.execute("""
                INSERT INTO user_logs (user_id, username, interactions, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username      = excluded.username,
                    interactions  = user_logs.interactions + excluded.interactions,
                    last_seen     = excluded.last_seen
            """, (uid, data["username"], data["interactions"], data["last_seen"]))
        await db.commit()

    user_log_queue.clear()

async def flush_user_logs_periodically():
    while True:
        await flush_user_logs()
        await asyncio.sleep(60)

async def generate_personality_notes(user_id: str, history: list):
    prompt = (
        "Analyze the following user's chat history and summarize their personality traits, "
        "interests, and communication style in 1–2 sentences. "
        "Keep it neutral, descriptive, and avoid any roleplay constraints.\n\n"
    )
    
    # Concatenate user messages only (ignore assistant)
    user_texts = [h["content"] for h in history if h["role"] == "user"]
    prompt += "\n".join(user_texts[-10:])
    
    try:
        response = await get_kobold_response([{"role": "system", "content": prompt}])
        return response.strip()
    except Exception as e:
        print(f"[Notes Generation Error] {e}")
        return None

async def update_personality_notes(user_id: str, notes: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO user_logs (user_id, personality_notes)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                personality_notes = excluded.personality_notes
        """, (user_id, notes))
        await db.commit()

async def maybe_update_personality_notes(user_id: str, username: str, history: list):
    if len(history) % 20 == 0:
        notes = await generate_personality_notes(user_id, history)
        if notes:
            await update_personality_notes(user_id, notes)

async def get_user_log(user_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM user_logs WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        await cursor.close()
        return row