import os
import aiosqlite
import asyncio
import datetime
import time
import re
from contextlib import asynccontextmanager
from src.utils.koboldcpp_util import get_kobold_response
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

# Pending notes queue for when model is unreachable
pending_notes_queue = asyncio.Queue()
notes_flush_task = None

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
            "write_queue_size": write_queue.qsize(),
            "pending_notes_queue_size": pending_notes_queue.qsize()
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_personalities (
                server_id TEXT PRIMARY KEY,
                personality_type TEXT NOT NULL,
                personality_value TEXT NOT NULL,
                is_custom BOOLEAN NOT NULL DEFAULT 0,
                locked BOOLEAN NOT NULL DEFAULT 0,
                last_updated TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS criminal_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                crime TEXT NOT NULL,
                arrested_by TEXT NOT NULL,
                jail_time INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES user_logs(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS civil_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id TEXT NOT NULL,
                plaintiff_id TEXT NOT NULL,
                defendant_id TEXT NOT NULL,
                complaint TEXT NOT NULL,
                amount INTEGER NOT NULL,
                verdict TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server_personalities ON server_personalities (server_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_criminal_user ON criminal_records (user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_criminal_server ON criminal_records (server_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_civil_plaintiff ON civil_cases (plaintiff_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_civil_defendant ON civil_cases (defendant_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_civil_server ON civil_cases (server_id)")

        await db.commit()

    await init_connection_pool()

async def delete_user_data(user_id: str):
    async with db_pool.get_connection() as db:
        await db.execute("DELETE FROM user_logs WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM server_interactions WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM criminal_records WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM civil_cases WHERE defendant_id = ?", (user_id,))
        await db.execute("DELETE FROM civil_cases WHERE plaintiff_id = ?", (user_id,))
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

# ============================================================================
# SERVER INTERACTIONS TRACKER
# ============================================================================
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

# ============================================================================
# USER LOGS
# ============================================================================
user_log_queue = {}
interaction_cache = {}  

# track how often to refresh notes
NOTES_UPDATE_INTERVAL = 10   # every 10 messages per user

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

async def flush_pending_notes_periodically():
    global notes_flush_task
    
    while True:
        await asyncio.sleep(30)
        
        if pending_notes_queue.empty():
            continue
        
        # Try to process one pending note
        try:
            pending_item = await asyncio.wait_for(
                pending_notes_queue.get(), 
                timeout=0.1
            )
            
            user_id = pending_item["user_id"]
            username = pending_item["username"]
            history = pending_item["history"]
            is_update = pending_item["is_update"]
            
            if is_update:
                old_notes = pending_item.get("old_notes", "")
                notes = await _try_update_notes(username, history, old_notes)
            else:
                notes = await _try_generate_notes(user_id, username, history)
            
            if notes:
                await update_personality_notes_with_username(user_id, username, notes)
                logger.info(f"[Flushed Pending Notes] {username}")
            else:
                # Failed again, put it back in queue
                await pending_notes_queue.put(pending_item)
                logger.debug(f"[Notes Flush Failed] Requeued for {username}")
                
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.exception(f"[Notes Flush Error] {e}")

async def _try_generate_notes(user_id: str, username: str, history: list) -> str | None:
    user_texts = [
        h["content"] for h in history 
        if h.get("role") == "user" and h.get("name") == username
    ]
    
    if len(user_texts) < 3:
        return None
    
    prompt = (
        f"Analyze {username}'s chat messages and summarize their personality traits, "
        "interests, and communication style in 1-2 sentences. "
        "Be specific, neutral, and descriptive.\n\n"
        f"Messages from {username}:\n"
    )
    
    # Use last 15 messages from THIS user only
    prompt += "\n".join(user_texts[-15:])
    
    try:
        response = await get_kobold_response([{"role": "system", "content": prompt}])
        logger.debug(f"Generated notes for {user_id}.")
        return response.strip()
    except Exception as e:
        logger.debug(f"[Notes Generation Failed - Model Unreachable] {user_id}")
        return None

async def _try_update_notes(username: str, history: list, old_notes: str) -> str | None:

    user_msgs = [
        h["content"] for h in history 
        if h.get("role") == "user" and h.get("name") == username
    ]
    
    if len(user_msgs) < 3:
        return None
    
    recent = "\n".join(user_msgs[-10:])
    
    if not recent.strip():
        return None
    
    prompt = (
        f"Existing notes about {username}: {old_notes}\n\n"
        f"Recent messages from {username}:\n{recent}\n\n"
        "Update the personality summary based on new information. "
        "Keep it 1-2 sentences, neutral, and descriptive. "
        "If nothing new is learned, reply with 'no changes'."
    )

    try:
        response = await get_kobold_response([{"role": "system", "content": prompt}])
        cleaned = response.strip()

        if cleaned.lower() in ["", "no changes", "none"]:
            return None
        
        if not significant_change(old_notes, cleaned):
            return None

        return cleaned
    except Exception as e:
        logger.debug(f"[Notes Update Failed - Model Unreachable] {username}")
        return None

async def generate_personality_notes(user_id: str, username:str, history: list):

    notes = await _try_generate_notes(user_id, username, history)
    
    if notes is None:
        # Queue for later if model is unreachable
        await pending_notes_queue.put({
            "user_id": user_id,
            "username": username,
            "history": history,
            "is_update": False
        })
        logger.info(f"[Notes Queued] {username} - will retry when model available")
        return None
    
    return notes

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

async def update_personality_notes_with_username(user_id: str, username: str, notes: str):

    async with db_pool.get_connection() as db:
        # Check if user exists
        cursor = await db.execute("SELECT user_id FROM user_logs WHERE user_id = ?", (user_id,))
        exists = await cursor.fetchone()
        await cursor.close()
        
        if exists:
            # User exists, just update notes
            await db.execute("""
                UPDATE user_logs 
                SET personality_notes = ?
                WHERE user_id = ?
            """, (notes, user_id))
        else:
            # User doesn't exist, create entry with notes
            await db.execute("""
                INSERT INTO user_logs (user_id, username, interactions, last_seen, personality_notes)
                VALUES (?, ?, 0, NULL, ?)
            """, (user_id, username, notes))
        
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
    if not log:
        return
    
    user_msgs = [
        h["content"] for h in history 
        if h.get("role") == "user" and h.get("name") == username
    ]
    
    if len(user_msgs) < 3:
        return
    
    recent = "\n".join(user_msgs[-10:])
    
    if not recent.strip():
        return

    if log[4]:
        old_notes = log[4]
        
        # Try to update with fallback queueing
        notes = await _try_update_notes(username, history, old_notes)
        
        if notes is None:
            # Model unreachable, queue for later
            await pending_notes_queue.put({
                "user_id": user_id,
                "username": username,
                "history": history,
                "is_update": True,
                "old_notes": old_notes
            })
            logger.info(f"[Notes Update Queued] {username}")
            return
        
        await update_personality_notes_with_username(user_id, username, notes)
        logger.info(f"[Notes Updated] {username}: {notes}")
    else:
        notes = await generate_personality_notes(user_id, username, history)
        if notes:
            await update_personality_notes_with_username(user_id, username, notes)

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

async def generate_notes_from_messages(server_id: str, channel_id: str, messages: list, min_messages: int = 50) -> dict:

    # Group messages by user
    user_messages = {}
    for msg in messages:
        if msg.get("role") == "user" and msg.get("name"):
            username = msg.get("name")
            content = msg.get("content", "")
            
            # Try to extract user_id if embedded (format: "username" or could be user_id)
            # This assumes you're storing consistent identifiers
            if username not in user_messages:
                user_messages[username] = []
            user_messages[username].append(content)
    
    # Generate notes for users meeting threshold
    results = {}
    for username, messages_list in user_messages.items():
        if len(messages_list) < min_messages:
            continue
        
        # Take last 50 messages for analysis
        recent_msgs = messages_list[-50:]
        
        prompt = (
            f"Analyze {username}'s chat messages and summarize their personality traits, "
            "interests, and communication style in 1-2 sentences. "
            "Be specific, neutral, and descriptive.\n\n"
            f"Messages from {username}:\n"
            + "\n".join(recent_msgs)
        )
        
        try:
            response = await get_kobold_response([{"role": "system", "content": prompt}])
            notes = response.strip()
            results[username] = notes
            logger.info(f"[Bulk Notes Generated] {username}")
        except Exception as e:
            logger.error(f"[Bulk Notes Error] {username}: {e}")
            results[username] = None
    
    return results

# ============================================================================
# PERSONALITY DATABASE FUNCTIONS
# ============================================================================

async def save_server_personality(
    server_id: str, 
    personality_type: str,
    personality_value: str,
    is_custom: bool = False
):
    async with db_pool.get_connection() as db:
        await db.execute("""
            INSERT INTO server_personalities 
                (server_id, personality_type, personality_value, is_custom, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(server_id) DO UPDATE SET
                personality_type = excluded.personality_type,
                personality_value = excluded.personality_value,
                is_custom = excluded.is_custom,
                last_updated = excluded.last_updated
        """, (
            server_id, 
            personality_type, 
            personality_value, 
            is_custom,
            datetime.datetime.now(datetime.timezone.utc)
        ))
        await db.commit()
    
    logger.debug(f"Saved personality for server {server_id}: {personality_value}")

async def load_server_personality(server_id: str) -> dict | None:
    async with db_pool.get_connection() as db:
        cursor = await db.execute("""
            SELECT personality_type, personality_value, is_custom, locked
            FROM server_personalities 
            WHERE server_id = ?
        """, (server_id,))
        row = await cursor.fetchone()
        await cursor.close()
        
        if row:
            return {
                "type": row[0],
                "value": row[1],
                "is_custom": bool(row[2]),
                "locked": bool(row[3])
            }
        return None

async def delete_server_personality(server_id: str):
    async with db_pool.get_connection() as db:
        await db.execute(
            "DELETE FROM server_personalities WHERE server_id = ?",
            (server_id,)
        )
        await db.commit()
    
    logger.debug(f"Deleted personality for server {server_id}")

async def load_all_server_personalities() -> dict:
    personalities = {}
    
    async with db_pool.get_connection() as db:
        async with db.execute("""
            SELECT server_id, personality_type, personality_value, is_custom
            FROM server_personalities
        """) as cursor:
            async for row in cursor:
                server_id = row[0]
                personalities[server_id] = {
                    "type": row[1],
                    "value": row[2],
                    "is_custom": bool(row[3])
                }
    
    return personalities

async def set_server_personality_lock(server_id: str, locked: bool):
    async with db_pool.get_connection() as db:
        await db.execute("""
            INSERT INTO server_personalities (server_id, personality_type, personality_value, is_custom, locked)
            VALUES (?, 'standard', 'Default', 0, ?)
            ON CONFLICT(server_id) DO UPDATE SET locked = excluded.locked
        """, (server_id, locked))
        await db.commit()

async def get_server_personality_lock(server_id: str) -> bool:
    async with db_pool.get_connection() as db:
        cursor = await db.execute(
            "SELECT locked FROM server_personalities WHERE server_id = ?",
            (server_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        
        if row:
            return bool(row[0])
        return False
    
# ============================================================================
# CRIMINAL RECORD FUNCTIONS
# ============================================================================

async def add_crime_record(
    user_id: str,
    server_id: str, 
    crime: str,
    arrested_by: str,
    jail_time: int = 0
):
    
    async with db_pool.get_connection() as db:
        await db.execute("""
            INSERT INTO criminal_records 
                (user_id, server_id, crime, arrested_by, jail_time, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            server_id,
            crime,
            arrested_by,
            jail_time,
            datetime.datetime.now(datetime.timezone.utc).isoformat()
        ))
        await db.commit()
    
    logger.info(f"[Crime Recorded] {user_id} arrested for {crime} - {jail_time} years")


async def get_criminal_record(user_id: str, server_id: str, limit: int = 5):
    async with db_pool.get_connection() as db:
        # Get recent crimes
        cursor = await db.execute("""
            SELECT crime, arrested_by, jail_time, timestamp
            FROM criminal_records
            WHERE user_id = ? AND server_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (user_id, server_id, limit))
        crimes = await cursor.fetchall()
        await cursor.close()
        
        # Get total statistics
        cursor = await db.execute("""
            SELECT 
                COUNT(*) as total_crimes,
                SUM(jail_time) as total_jail_time,
                MAX(jail_time) as longest_sentence
            FROM criminal_records
            WHERE user_id = ? AND server_id = ?
        """, (user_id, server_id))
        stats = await cursor.fetchone()
        await cursor.close()
        
        return {
            "crimes": crimes,
            "total_crimes": stats[0] if stats else 0,
            "total_jail_time": stats[1] if stats else 0,
            "longest_sentence": stats[2] if stats else 0
        }

async def get_server_most_wanted(server_id: str, limit: int = 10):
    async with db_pool.get_connection() as db:
        cursor = await db.execute("""
            SELECT 
                user_id,
                COUNT(*) as crime_count,
                SUM(jail_time) as total_time
            FROM criminal_records
            WHERE server_id = ?
            GROUP BY user_id
            ORDER BY total_time DESC
            LIMIT ?
        """, (server_id, limit))
        most_wanted = await cursor.fetchall()
        await cursor.close()
        
        return most_wanted

async def clear_criminal_record(user_id: str, server_id: str):
    async with db_pool.get_connection() as db:
        await db.execute("""
            DELETE FROM criminal_records
            WHERE user_id = ? AND server_id = ?
        """, (user_id, server_id))
        await db.commit()
    
    logger.info(f"[Record Cleared] {user_id} in server {server_id}")

async def get_crime_statistics(server_id: str):
    async with db_pool.get_connection() as db:
        # Most common crimes
        cursor = await db.execute("""
            SELECT crime, COUNT(*) as count
            FROM criminal_records
            WHERE server_id = ?
            GROUP BY crime
            ORDER BY count DESC
            LIMIT 5
        """, (server_id,))
        common_crimes = await cursor.fetchall()
        await cursor.close()
        
        # Total statistics
        cursor = await db.execute("""
            SELECT 
                COUNT(*) as total_arrests,
                COUNT(DISTINCT user_id) as unique_criminals,
                SUM(jail_time) as total_jail_time
            FROM criminal_records
            WHERE server_id = ?
        """, (server_id,))
        stats = await cursor.fetchone()
        await cursor.close()
        
        return {
            "common_crimes": common_crimes,
            "total_arrests": stats[0] if stats else 0,
            "unique_criminals": stats[1] if stats else 0,
            "total_jail_time": stats[2] if stats else 0
        }
    
async def add_civil_case(
    server_id: str,
    plaintiff_id: str,
    defendant_id: str,
    complaint: str,
    amount: int,
    verdict: str
):
    
    async with db_pool.get_connection() as db:
        await db.execute("""
            INSERT INTO civil_cases 
                (server_id, plaintiff_id, defendant_id, complaint, amount, verdict, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            server_id,
            plaintiff_id,
            defendant_id,
            complaint,
            amount,
            verdict,
            datetime.datetime.now(datetime.timezone.utc).isoformat()
        ))
        await db.commit()
    
    logger.info(f"[Civil Case] {plaintiff_id} vs {defendant_id} - Verdict: {verdict}, Amount: ${amount}")

async def get_civil_record(user_id: str, server_id: str):
    async with db_pool.get_connection() as db:
        # Cases as plaintiff
        cursor = await db.execute("""
            SELECT 
                COUNT(*) as total_filed,
                SUM(CASE WHEN verdict = 'guilty' THEN 1 ELSE 0 END) as won,
                SUM(CASE WHEN verdict = 'guilty' THEN amount ELSE 0 END) as money_won
            FROM civil_cases
            WHERE plaintiff_id = ? AND server_id = ?
        """, (user_id, server_id))
        plaintiff_stats = await cursor.fetchone()
        await cursor.close()
        
        # Cases as defendant
        cursor = await db.execute("""
            SELECT 
                COUNT(*) as total_sued,
                SUM(CASE WHEN verdict = 'guilty' THEN 1 ELSE 0 END) as lost,
                SUM(CASE WHEN verdict = 'guilty' THEN amount ELSE 0 END) as money_lost
            FROM civil_cases
            WHERE defendant_id = ? AND server_id = ?
        """, (user_id, server_id))
        defendant_stats = await cursor.fetchone()
        await cursor.close()
        
        # Recent cases (last 5)
        cursor = await db.execute("""
            SELECT 
                plaintiff_id,
                defendant_id,
                complaint,
                amount,
                verdict,
                timestamp,
                CASE 
                    WHEN plaintiff_id = ? THEN 'plaintiff'
                    ELSE 'defendant'
                END as role
            FROM civil_cases
            WHERE (plaintiff_id = ? OR defendant_id = ?) AND server_id = ?
            ORDER BY timestamp DESC
            LIMIT 5
        """, (user_id, user_id, user_id, server_id))
        recent_cases = await cursor.fetchall()
        await cursor.close()
        
        return {
            # Plaintiff stats (handle None values)
            "cases_filed": plaintiff_stats[0] if plaintiff_stats and plaintiff_stats[0] else 0,
            "cases_won": plaintiff_stats[1] if plaintiff_stats and plaintiff_stats[1] else 0,
            "money_won": plaintiff_stats[2] if plaintiff_stats and plaintiff_stats[2] else 0,
            
            # Defendant stats (handle None values)
            "times_sued": defendant_stats[0] if defendant_stats and defendant_stats[0] else 0,
            "cases_lost": defendant_stats[1] if defendant_stats and defendant_stats[1] else 0,
            "money_lost": defendant_stats[2] if defendant_stats and defendant_stats[2] else 0,
            
            # Recent activity
            "recent_cases": recent_cases
        }

# ============================================================================
# WORLD MEMORY SYSTEM
# ============================================================================
world_histories = {} # {server_id: [ {author, content}, ... ]}
world_update_cooldowns = {}
WORLD_UPDATE_MESSAGE_THRESHOLD = 25
WORLD_UPDATE_COOLDOWN = 120

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

async def get_world_context(server_id: str, max_facts: int = 15) -> str:    
    async with db_pool.get_connection() as db:
        async with db.execute("""
            SELECT key, value, last_updated 
            FROM world_state 
            WHERE server_id = ?
            ORDER BY last_updated DESC
            LIMIT ?
        """, (server_id, max_facts)) as cursor:
            facts = []
            async for row in cursor:
                key = row[0].replace("_", " ").title()
                value = row[1]
                facts.append(f"• {key}: {value}")
    
    if not facts:
        return ""
    
    return "Current World State:\n" + "\n".join(facts)

async def summarize_world_and_update(server_id: str, recent_messages: list):
    if not recent_messages or len(recent_messages) < 10:
        return

    # Take last 30 messages
    snippet = "\n".join([
        f"{m['author']}: {m['content']}" 
        for m in recent_messages[-30:]
    ])

    prompt = (
        "Extract factual updates about the world/story/setting from these messages.\n"
        "Focus ONLY on:\n"
        "- Major events (battles, discoveries, arrivals/departures)\n"
        "- Character status changes (injuries, transformations, relationships)\n"
        "- Location changes (new places discovered, destruction)\n"
        "- Important objects or items introduced\n\n"
        "Format: key: value (e.g. 'throne_status: King overthrown by rebels')\n"
        "Return 1-3 updates ONLY if significant events occurred.\n"
        "If nothing important happened, reply with: no changes\n\n"
        f"Messages:\n{snippet}\n\n"
        "New facts:"
    )

    messages = [
        {"role": "system", "content": "You track key facts about a shared fictional world. Be specific and concise."},
        {"role": "user", "content": prompt}
    ]

    try:
        response = await get_kobold_response(messages)
        cleaned = response.strip().lower()

        if cleaned in ["", "no changes", "none", "no updates"]:
            logger.debug(f"[World] No updates for server {server_id}")
            return

        # Parse key:value pairs
        updates_count = 0
        for line in response.splitlines():
            match = re.match(r"^\s*([^:]+)\s*:\s*(.+)$", line)
            if match:
                key, value = match.groups()
                key_clean = key.strip().lower().replace(" ", "_")
                await add_world_fact(server_id, key_clean, value.strip())
                updates_count += 1

        if updates_count > 0:
            logger.info(f"[World Updated] Server {server_id}: {updates_count} facts")

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
    
    # Need minimum messages
    if len(history) < WORLD_UPDATE_MESSAGE_THRESHOLD:
        return

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    last_update = world_update_cooldowns.get(server_id, 0)

    # Check cooldown
    if now - last_update < WORLD_UPDATE_COOLDOWN:
        return

    # Perform update
    await summarize_world_and_update(server_id, history)
    world_update_cooldowns[server_id] = now
    
    # Keep some history for context
    world_histories[server_id] = world_histories[server_id][-10:]

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

async def list_world_facts(server_id: str) -> list:    
    async with db_pool.get_connection() as db:
        async with db.execute("""
            SELECT key, value, last_updated 
            FROM world_state 
            WHERE server_id = ?
            ORDER BY last_updated DESC
        """, (server_id,)) as cursor:
            return [
                {
                    "key": row[0],
                    "value": row[1],
                    "updated": row[2]
                }
                async for row in cursor
            ]


async def manual_world_update(server_id: str, key: str, value: str):    
    key_clean = key.lower().replace(" ", "_")
    await add_world_fact(server_id, key_clean, value)
    logger.info(f"[World Manual Update] {server_id}: {key_clean} = {value}")

# ============================================================================
# CONTEXT BUILDER
# ============================================================================
async def build_context(user_id: str, username: str, server_id: str | None = None) -> list:
    context_msgs = []

    # World context
    if server_id:
        world_context = await get_world_context(server_id)
        if world_context:
            context_msgs.append({
                "role": "system",
                "content": f"World context for this server:\n{world_context}"
            })

    return context_msgs
