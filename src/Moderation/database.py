import os
import aiosqlite
import asyncio
import datetime
import time
import re
from contextlib import asynccontextmanager
from src.utils.kobaldcpp_util import get_kobold_response
from src.utils.memory_util import significant_change
from src.moderation.logging import logger

DB_PATH =  "data/user_data.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# User log cache configuration
USER_LOG_CACHE_TTL = 120  # 2 minutes cache lifetime
user_log_cache = {}  # {user_id: (log_data, timestamp)}

# Connection pool configuration
MAX_POOL_SIZE = 3
MIN_POOL_SIZE = 2
CONNECTION_TIMEOUT = 30

class ConnectionPool:
    def __init__(self, db_path: str, min_size: int = MIN_POOL_SIZE, max_size: int = MAX_POOL_SIZE):
        self.db_path = db_path
        self.min_size = min_size
        self.max_size = max_size
        self._pool = asyncio.Queue(maxsize=max_size)
        self._size = 0
        self._lock = asyncio.Lock()
    
    async def init(self):
        for _ in range(self.min_size):
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row
            await self._pool.put(conn)
            self._size += 1
        logger.info(f"Connection pool initialized with {self.min_size} connections")
    
    async def acquire(self):
        try:
            # Try to get existing connection with timeout
            conn = await asyncio.wait_for(self._pool.get(), timeout=CONNECTION_TIMEOUT)
            return conn
        except asyncio.TimeoutError:
            # Pool exhausted and no connections available
            async with self._lock:
                if self._size < self.max_size:
                    # Create new connection if under max size
                    conn = await aiosqlite.connect(self.db_path)
                    conn.row_factory = aiosqlite.Row
                    self._size += 1
                    logger.debug(f"Created new connection. Pool size: {self._size}")
                    return conn
                else:
                    # Wait indefinitely if at max capacity
                    return await self._pool.get()
    
    async def release(self, conn):
        try:
            self._pool.put_nowait(conn)
        except asyncio.QueueFull:
            # Pool is full, close the connection
            await conn.close()
            async with self._lock:
                self._size -= 1
            logger.debug(f"Closed excess connection. Pool size: {self._size}")
    
    async def close(self):
        while not self._pool.empty():
            conn = await self._pool.get()
            await conn.close()
            self._size -= 1
        logger.info("Connection pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        conn = await self.acquire()
        try:
            yield conn
        finally:
            await self.release(conn)

# Global connection pool instance
db_pool = None

async def init_connection_pool():
    global db_pool
    if db_pool is None:
        db_pool = ConnectionPool(DB_PATH)
        await db_pool.init()

async def close_connection_pool():
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None

def get_pool_stats():
    if db_pool:
        return {
            "pool_size": db_pool._size,
            "available_connections": db_pool._pool.qsize(),
            "max_size": db_pool.max_size,
            "write_queue_size": write_queue.qsize()
        }
    return None

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

    await init_connection_pool()

async def delete_user_data(user_id: str):
    async with db_pool.get_connection() as db:
        await db.execute("DELETE FROM user_logs WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM server_interactions WHERE user_id = ?", (user_id,))
        await db.commit()

    if user_id in user_log_cache:
        del user_log_cache[user_id]

async def reset_database():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DROP TABLE IF EXISTS server_interactions")
        await db.execute("DROP TABLE IF EXISTS user_logs")
        await db.execute("DROP TABLE IF EXISTS world_state")
        await db.commit()
    
    user_log_cache.clear()

    await init_db()

#---- Functions for 'server_interactions' ----#
write_queue = asyncio.Queue()

# Batching configuration
BATCH_SIZE = 10           # Process up to 20 increments at once
BATCH_TIMEOUT = 2.0       # Wait max 1 second to accumulate batch
FLUSH_INTERVAL = 5.0      # Force flush every 5 seconds even with small batches

async def queue_increment(server_id: str, user_id: str):
    await write_queue.put((server_id, user_id))

async def increment_server_interaction():
    try:
        last_flush = time.time()
        
        while True:
            batch = []
            start_time = time.time()
            
            # Collect items for batch
            while len(batch) < BATCH_SIZE:
                time_remaining = BATCH_TIMEOUT - (time.time() - start_time)
                
                if time_remaining <= 0:
                    break
                
                try:
                    # Wait for next item with remaining timeout
                    item = await asyncio.wait_for(write_queue.get(), timeout=time_remaining)
                    batch.append(item)
                    write_queue.task_done()
                except asyncio.TimeoutError:
                    break
            
            # Force flush if enough time has passed, even with small batch
            time_since_flush = time.time() - last_flush
            if not batch and time_since_flush < FLUSH_INTERVAL:
                await asyncio.sleep(0.1)  # Brief sleep to avoid busy loop
                continue
            
            if batch:
                await _flush_interaction_batch(batch)
                last_flush = time.time()
                logger.debug(f"Flushed batch of {len(batch)} interaction increments")
            
    except Exception as e:
        logger.exception(f"Critical error in increment_server_interaction: {e}")

async def _flush_interaction_batch(batch: list):
    if not batch:
        return
    
    try:
        async with db_pool.get_connection() as db:
            # Group increments by (server_id, user_id) to handle duplicates
            increment_counts = {}
            for server_id, user_id in batch:
                key = (server_id, user_id)
                increment_counts[key] = increment_counts.get(key, 0) + 1
            
            # Execute all updates in a single transaction
            for (server_id, user_id), count in increment_counts.items():
                await db.execute("""
                    INSERT INTO server_interactions (server_id, user_id, count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(server_id, user_id)
                    DO UPDATE SET count = count + ?
                """, (server_id, user_id, count, count))
            
            await db.commit()
            
    except aiosqlite.Error as e:
        logger.error(f"Database error in _flush_interaction_batch: {e}")

async def show_server_interactions_user(server_id: str, user_id: str) -> int:
    try:
        async with db_pool.get_connection() as db:
            cursor = await db.execute("SELECT count FROM server_interactions WHERE server_id=? AND user_id=?", (server_id, user_id))
            row = await cursor.fetchone()
            count = row[0] if row else 0
            return count
    except aiosqlite.Error as e:
        print(f"Database error in show_server_interactions_user: {e}")

async def show_server_interactions_leaderboard(server_id: str):
    try:
        async with db_pool.get_connection() as db:
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

    async with db_pool.get_connection() as db:
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

    for uid in user_log_queue.keys():
        if uid in user_log_cache:
            del user_log_cache[uid]

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
        logger.debug(f"Generated notes for {user_id}.")
        return response.strip()
    except Exception as e:
        print(f"[Notes Generation Error] {e}")
        logger.exception(f"[Notes Generation Error] {e}")
        return None

async def update_personality_notes(user_id: str, notes: str):
    async with db_pool.get_connection() as db:
        await db.execute("""
            INSERT INTO user_logs (user_id, personality_notes)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                personality_notes = excluded.personality_notes
        """, (user_id, notes))
        await db.commit()

    if user_id in user_log_cache:
        del user_log_cache[user_id]

async def get_personality_context(user_id: str, username: str) -> str:
    log = await get_user_log_cached(user_id)
    if log and log[4]:
        return f"Notes about {username}: {log[4]}"
    return ""

async def maybe_queue_notes_update(user_id: str, username: str, history: list, interactions: int):
    if interactions % NOTES_UPDATE_INTERVAL != 0:
        return

    log = await get_user_log_cached(user_id)
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
                
                if not significant_change(old_notes, cleaned):
                    return  # skip if not much new

                await update_personality_notes(user_id, cleaned)
                logger.info(f"[Notes Updated] {username}: {cleaned}")
            except Exception as e:
                logger.exception(f"[Notes Update Error] {e}")
        else:
            notes = await generate_personality_notes(user_id, history)
            await update_personality_notes(user_id, notes)

async def get_user_log(user_id: str):
    async with db_pool.get_connection() as db:
        cursor = await db.execute("SELECT * FROM user_logs WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        await cursor.close()
        return row
    
async def get_user_log_cached(user_id: str):
    now = time.time()
    
    # Check if cached and still valid
    if user_id in user_log_cache:
        log_data, timestamp = user_log_cache[user_id]
        if now - timestamp < USER_LOG_CACHE_TTL:
            return log_data
        else:
            # Cache expired, remove it
            del user_log_cache[user_id]
    
    # Fetch from database
    log = await get_user_log(user_id)
    
    # Cache the result (even if None)
    user_log_cache[user_id] = (log, now)
    
    return log

def invalidate_user_log_cache(user_id: str):
    if user_id in user_log_cache:
        del user_log_cache[user_id]

def clear_user_log_cache():
    user_log_cache.clear()

async def get_user_interactions(user_id: str) -> int:
    # check memory first
    if user_id in interaction_cache:
        return interaction_cache[user_id]

    # fallback: fetch from DB
    log = await get_user_log_cached(user_id)
    if log:
        count = log[2]
        interaction_cache[user_id] = count
        return count

    return 0

async def load_interaction_cache():
    global interaction_cache
    interaction_cache.clear()

    async with db_pool.get_connection() as db:
        async with db.execute("SELECT user_id, interactions FROM user_logs") as cursor:
            async for row in cursor:
                user_id, interactions = row
                interaction_cache[user_id] = interactions

    print(f"[Cache Loaded] {len(interaction_cache)} users restored from DB")

#---- Functions for World Context ----#
world_histories = {} # {server_id: [ {author, content}, ... ]}
world_update_cooldowns = {}

async def add_world_fact(server_id: str, key: str, value: str):
    async with db_pool.get_connection() as db:
        await db.execute("""
            INSERT INTO world_state (server_id, key, value, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(server_id, key) DO UPDATE SET
                value = excluded.value,
                last_updated = excluded.last_updated
        """, (server_id, key, value, datetime.datetime.now(datetime.timezone.utc)))
        await db.commit()

async def get_world_context(server_id: str) -> str:
    async with db_pool.get_connection() as db:
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
        for line in response.splitlines():
            match = re.match(r"^\s*([^:]+)\s*:\s*(.+)$", line)
            if match:
                key, value = match.groups()
                await add_world_fact(server_id, key.strip(), value.strip())

        logger.info(f"[World Updated] {response}")

    except Exception as e:
        logger.exception(f"[World Summarizer Error] {e}")

def add_to_world_history(server_id: str, author: str, content: str):
    if server_id not in world_histories:
        world_histories[server_id] = []
    world_histories[server_id].append({"author": author, "content": content})
    if len(world_histories[server_id]) > 50:
        world_histories[server_id] = world_histories[server_id][-50:]

async def maybe_update_world(server_id: str):
    history = world_histories.get(server_id, [])
    if len(history) < 30:
        return

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    last_update = world_update_cooldowns.get(server_id, 0)

    if len(history) >= 30 and now - last_update > 60:
        await summarize_world_and_update(server_id, history)
        world_update_cooldowns[server_id] = now
        world_histories[server_id] = []

async def delete_world_entry(server_id: str, key: str):
    async with db_pool.get_connection() as db:
        await db.execute(
            "DELETE FROM world_state WHERE server_id = ? AND key = ?",
            (server_id, key)
        )
        await db.commit()

async def delete_world_context(server_id: str):
    async with db_pool.get_connection() as db:
        await db.execute("DELETE FROM world_state WHERE server_id = ?", (server_id,))
        await db.commit()

#---- Context Builder for responses ----#
async def build_context(user_id: str, username: str, server_id: str | None = None) -> list:
    context_msgs = []

    # Personality notes
    log = await get_user_log_cached(user_id)
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
