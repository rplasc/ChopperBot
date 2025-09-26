import os
import aiosqlite
import asyncio
import datetime
from utils.kobaldcpp_util import get_kobold_response

DB_PATH =  "data/bot_data.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Initializes tables
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_interactions (
                server_id TEXT,
                user_id TEXT,
                count INTEGER,
                PRIMARY KEY (server_id, user_id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server_id ON server_interactions (server_id)")
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

#---- Functions for 'server_interactions' ----#
write_queue = asyncio.Queue()
async def queue_increment(server_id: str, user_id: str):
    await write_queue.put((server_id, user_id))

async def increment_yap():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
             while True:
                server_id, user_id = await write_queue.get()
                await db.execute("""
                    INSERT INTO server_interactions (server_id, user_id, count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(server_id, user_id)
                    DO UPDATE SET count = count + 1
                """, (server_id, user_id))
                await db.commit()
                write_queue.task_done()
    except aiosqlite.Error as e:
        print(f"Database error in increment_yap: {e}")

async def show_server_interactions_user(server_id: str, user_id: str) -> int:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT count FROM server_interactions WHERE server_id=? AND user_id=?", (server_id, user_id))
            row = await cursor.fetchone()
            count = row[0] if row else 0
            return count
    except aiosqlite.Error as e:
        print(f"Database error in show_server_interactions_user: {e}")

async def show_server_interactions_leaderboard(server_id: str):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id, count FROM server_interactions WHERE server_id=? ORDER BY count DESC LIMIT 10",
                (server_id,)
            )
            top_users = await cursor.fetchall()        
            return top_users
    except aiosqlite.Error as e:
        print(f"Database error in show_server_interactions_leaderboard: {e}")

#---- Functions for User Logs ----#
user_log_queue = {}
interaction_cache = {}  

# track how often to refresh notes
NOTES_UPDATE_INTERVAL = 10   # every 10 messages per use

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
    
    global interaction_cache

    async with aiosqlite.connect(DB_PATH) as db:
        for uid, data in user_log_queue.items():
            interactions = interaction_cache.get(uid, data["interactions"])
            await db.execute("""
                INSERT INTO user_logs (user_id, username, interactions, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    interactions = excluded.interactions,
                    last_seen = excluded.last_seen
            """, (uid, data["username"], interactions, data["last_seen"]))
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

async def get_personality_context(user_id: str, username: str) -> str:
    log = await get_user_log(user_id)
    if log and log[4]:
        return f"Notes about {username}: {log[4]}"
    return ""

async def update_personality_notes_incremental(user_id: str, username: str, history: list):
    # Get old notes
    log = await get_user_log(user_id)
    old_notes = log[4] if log and log[4] else "No notes yet."

    # Use the last N messages from the user
    user_msgs = [h["content"] for h in history if h["role"] == "user"]
    recent = "\n".join(user_msgs[-5:]) if user_msgs else "No recent activity."

    prompt = (
        f"Current notes about {username}: {old_notes}\n\n"
        f"Recent activity:\n{recent}\n\n"
        "Update the notes by adding or modifying details if needed. "
        "Keep them concise, factual, and in third person. Do not erase useful info."
    )

    messages = [
        {"role": "system", "content": "You maintain evolving personality notes about users."},
        {"role": "user", "content": prompt}
    ]

    try:
        new_notes = await get_kobold_response(messages)
        await update_personality_notes(user_id, new_notes.strip())
    except Exception as e:
        print(f"[Personality Notes Update Error] {e}")

async def maybe_queue_notes_update(user_id: str, username: str, history: list, interactions: int):
    if interactions % NOTES_UPDATE_INTERVAL != 0:
        return

    log = await get_user_log(user_id)
    old_notes = log[4] if log and log[4] else "No notes yet."

    # last few user messages
    user_msgs = [h["content"] for h in history if h["role"] == "user"]
    recent = "\n".join(user_msgs[-5:]) if user_msgs else "No recent activity."

    prompt = (
        f"Current notes about {username}: {old_notes}\n\n"
        f"Recent activity:\n{recent}\n\n"
        "Update the notes by adding or modifying details if needed. "
        "Keep them concise, factual, and in third person. "
        "Do not erase useful information unless it is outdated or wrong."
    )

    messages = [
        {"role": "system", "content": "You are a neutral observer. Maintain evolving personality notes about users."},
        {"role": "user", "content": prompt}
    ]

    try:
        new_notes = await get_kobold_response(messages)
        await update_personality_notes(user_id, new_notes.strip())
        print(f"[Notes Updated] {username}: {new_notes}")
    except Exception as e:
        print(f"[Notes Update Error] {e}")

async def get_user_log(user_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM user_logs WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        await cursor.close()
        return row

async def get_user_interactions(user_id: str) -> int:
    # check memory first
    if user_id in interaction_cache:
        return interaction_cache[user_id]

    # fallback: fetch from DB
    log = await get_user_log(user_id)
    if log:
        count = log[2]  # interactions column
        interaction_cache[user_id] = count
        return count

    return 0

async def load_interaction_cache():
    global interaction_cache
    interaction_cache.clear()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, interactions FROM user_logs") as cursor:
            async for row in cursor:
                user_id, interactions = row
                interaction_cache[user_id] = interactions

    print(f"[Cache Loaded] {len(interaction_cache)} users restored from DB")
