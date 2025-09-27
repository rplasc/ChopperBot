import os
import aiosqlite
import asyncio
import datetime
import re
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS world_state (
                server_id TEXT,
                key TEXT,
                value TEXT,
                last_updated TEXT,
                PRIMARY KEY (server_id, key)
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

async def maybe_queue_notes_update(user_id: str, username: str, history: list, interactions: int):
    if interactions % NOTES_UPDATE_INTERVAL != 0:
        return

    log = await get_user_log(user_id)
    if log:
        if log[4]:

            old_notes = log[4]

            user_msgs = [h["content"] for h in history if h["role"] == "user"]
            recent = "\n".join(user_msgs[-10:]) if user_msgs else ""

            if not recent.strip():
                return

            prompt = (
                f"Existing notes about {username}: {old_notes}\n\n"
                f"Recent chat history:\n{recent}\n\n"
                "Update the personality summary of this user based on both the existing notes "
                "and the new chat history. "
                "Keep it 1–2 sentences, neutral, factual, and descriptive of traits/interests/communication style. "
                "If nothing new is learned, reply with 'no changes'."
            )

            try:
                response = await get_kobold_response([{"role": "system", "content": prompt}])
                cleaned = response.strip()

                if cleaned.lower() in ["", "no changes", "none"]:
                    return  # keep old notes unchanged

                await update_personality_notes(user_id, cleaned)
                print(f"[Notes Updated] {username}: {cleaned}")

            except Exception as e:
                print(f"[Notes Update Error] {e}")
        else:
            await generate_personality_notes(user_id, history)

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

#---- Functions for World Context ----#
world_histories = {} # {server_id: [ {author, content}, ... ]}
world_update_cooldowns = {}

async def add_world_fact(server_id: str, key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO world_state (server_id, key, value, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(server_id, key) DO UPDATE SET
                value = excluded.value,
                last_updated = excluded.last_updated
        """, (server_id, key, value, datetime.datetime.now(datetime.timezone.utc)))
        await db.commit()

async def get_world_context(server_id: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT key, value FROM world_state WHERE server_id = ?
        """, (server_id,)) as cursor:
            facts = [f"{row[0]}: {row[1]}" async for row in cursor]
    return "\n".join(facts) if facts else ""

async def summarize_world_and_update(server_id: str, recent_messages: list):
    if not recent_messages:
        return

    # Take the last 20 messages from the server
    snippet = "\n".join([f"{m['author']}: {m['content']}" for m in recent_messages[-20:]])

    prompt = (
        "Current task: Identify factual world events or states from these RP messages. "
        "Only return clear, significant updates (e.g., battles, discoveries, status changes). "
        "Format as short key: value pairs, like 'capital_city: Rebels breached the gates'. "
        "If nothing meaningful occurred, reply with 'no changes'. "
        "Do not speculate. Do not describe inactivity or filler dialogue.\n\n"
        f"Messages:\n{snippet}\n\n"
        "Return 1–3 new or updated facts only."
    )

    messages = [
        {"role": "system", "content": "You maintain evolving facts about a shared fictional world."},
        {"role": "user", "content": prompt}
    ]

    try:
        response = await get_kobold_response(messages)
        cleaned = response.strip().lower()

        if cleaned in ["", "no changes", "none"]:
            return  # no update this round

        # Parse key:value pairs safely
        import re
        for line in response.splitlines():
            match = re.match(r"^\s*([^:]+)\s*:\s*(.+)$", line)
            if match:
                key, value = match.groups()
                await add_world_fact(server_id, key.strip(), value.strip())

        print(f"[World Updated] {response}")

    except Exception as e:
        print(f"[World Summarizer Error] {e}")

def add_to_world_history(server_id: str, author: str, content: str):
    if server_id not in world_histories:
        world_histories[server_id] = []
    world_histories[server_id].append({"author": author, "content": content})
    if len(world_histories[server_id]) > 50:
        world_histories[server_id] = world_histories[server_id][-50:]

async def maybe_update_world(server_id: str):
    history = world_histories.get(server_id, [])
    if not history:
        return

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    last_update = world_update_cooldowns.get(server_id, 0)

    if len(history) % 30 == 0 and now - last_update > 60:  # 1 min cooldown
        await summarize_world_and_update(server_id, history)
        world_update_cooldowns[server_id] = now

#---- Context Builder for responses ----#
async def build_context(user_id: str, username: str, server_id: str | None = None) -> list:
    context_msgs = []

    # Personality notes
    log = await get_user_log(user_id)
    if log and log[4]:  # personality_notes column
        context_msgs.append({
            "role": "system",
            "content": f"Personality notes about {username}: {log[4]}"
        })

    # World context
    if server_id:
        world_context = await get_world_context(server_id)
        if world_context:
            context_msgs.append({
                "role": "system",
                "content": f"World context for this server:\n{world_context}"
            })

    return context_msgs
