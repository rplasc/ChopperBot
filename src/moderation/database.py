import os
import re
import json
import aiosqlite
import asyncio
import datetime
import time
from contextlib import asynccontextmanager
from src.services.llm_service import chat_completion
from src.services.memory_service import (
    FACT_EXTRACTION_INSTRUCTIONS,
    build_fts_query,
    clamp_importance,
    parse_fact_lines,
    rerank_memories,
)
from src.moderation.logging import logger

DB_PATH = "data/user_data.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

# Connection pool
MAX_POOL_SIZE = 3
MIN_POOL_SIZE = 2
CONNECTION_TIMEOUT = 30

# User log cache
USER_LOG_CACHE_TTL = 120  # seconds

# Personality notes
NOTES_UPDATE_INTERVAL = 10   # regenerate notes every N messages per user
MAX_WORLD_FACTS = 15         # hard limit to prevent context bloat

# Channel long-term memory
CHANNEL_MEMORY_INTERVAL = 25  # store a channel summary every N messages
MAX_CHANNEL_MEMORIES = 50     # oldest pruned when exceeded

# ============================================================================
# IN-MEMORY STATE
# ============================================================================

user_log_cache: dict = {}     # {user_id: (log_data, timestamp)}
interaction_cache: dict = {}  # {user_id: interaction_count}
pending_notes_queue: asyncio.Queue = asyncio.Queue()

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
        await db.execute("CREATE INDEX IF NOT EXISTS idx_criminal_user ON criminal_records (user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_criminal_server ON criminal_records (server_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_civil_plaintiff ON civil_cases (plaintiff_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_civil_defendant ON civil_cases (defendant_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_civil_server ON civil_cases (server_id)")

        # ---- RAG: user_memories ----
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_memories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                category   TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_memories_user ON user_memories (user_id)")
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS user_memories_fts USING fts5(
                content,
                content='user_memories',
                content_rowid='id',
                tokenize='porter unicode61'
            )
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS umem_fts_insert
            AFTER INSERT ON user_memories BEGIN
                INSERT INTO user_memories_fts(rowid, content) VALUES (new.id, new.content);
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS umem_fts_delete
            AFTER DELETE ON user_memories BEGIN
                INSERT INTO user_memories_fts(user_memories_fts, rowid, content)
                VALUES ('delete', old.id, old.content);
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS umem_fts_update
            AFTER UPDATE ON user_memories BEGIN
                INSERT INTO user_memories_fts(user_memories_fts, rowid, content)
                VALUES ('delete', old.id, old.content);
                INSERT INTO user_memories_fts(rowid, content) VALUES (new.id, new.content);
            END
        """)

        # ---- RAG: world_state_fts ----
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS world_state_fts USING fts5(
                key, value,
                content='world_state',
                content_rowid='rowid',
                tokenize='porter unicode61'
            )
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS wstate_fts_insert
            AFTER INSERT ON world_state BEGIN
                INSERT INTO world_state_fts(rowid, key, value) VALUES (new.rowid, new.key, new.value);
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS wstate_fts_delete
            AFTER DELETE ON world_state BEGIN
                INSERT INTO world_state_fts(world_state_fts, rowid, key, value)
                VALUES ('delete', old.rowid, old.key, old.value);
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS wstate_fts_update
            AFTER UPDATE ON world_state BEGIN
                INSERT INTO world_state_fts(world_state_fts, rowid, key, value)
                VALUES ('delete', old.rowid, old.key, old.value);
                INSERT INTO world_state_fts(rowid, key, value) VALUES (new.rowid, new.key, new.value);
            END
        """)

        # ---- RAG: channel_memories ----
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_memories (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id    TEXT NOT NULL,
                channel_id   TEXT NOT NULL,
                summary      TEXT NOT NULL,
                participants TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_channel_memories_lookup
            ON channel_memories (server_id, channel_id)
        """)
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS channel_memories_fts USING fts5(
                summary,
                content='channel_memories',
                content_rowid='id',
                tokenize='porter unicode61'
            )
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS cmem_fts_insert
            AFTER INSERT ON channel_memories BEGIN
                INSERT INTO channel_memories_fts(rowid, summary) VALUES (new.id, new.summary);
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS cmem_fts_delete
            AFTER DELETE ON channel_memories BEGIN
                INSERT INTO channel_memories_fts(channel_memories_fts, rowid, summary)
                VALUES ('delete', old.id, old.summary);
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS cmem_fts_update
            AFTER UPDATE ON channel_memories BEGIN
                INSERT INTO channel_memories_fts(channel_memories_fts, rowid, summary)
                VALUES ('delete', old.id, old.summary);
                INSERT INTO channel_memories_fts(rowid, summary) VALUES (new.id, new.summary);
            END
        """)

        # ---- v2: per-user personality trait profiles ----
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_personality (
                user_id         TEXT PRIMARY KEY,
                curiosity       REAL NOT NULL DEFAULT 50,
                humor           REAL NOT NULL DEFAULT 50,
                logic           REAL NOT NULL DEFAULT 50,
                creativity      REAL NOT NULL DEFAULT 50,
                kindness        REAL NOT NULL DEFAULT 50,
                competitiveness REAL NOT NULL DEFAULT 50,
                confidence      REAL NOT NULL DEFAULT 50,
                updated_at      TEXT
            )
        """)

        # ---- v2 migration: importance column on user_memories ----
        cursor = await db.execute("PRAGMA table_info(user_memories)")
        columns = [row[1] for row in await cursor.fetchall()]
        await cursor.close()
        if "importance" not in columns:
            await db.execute(
                "ALTER TABLE user_memories ADD COLUMN importance INTEGER NOT NULL DEFAULT 3"
            )

        await db.commit()

        # ---- Migration: split legacy personality_notes blobs into user_memories ----
        cursor = await db.execute(
            "SELECT user_id, personality_notes FROM user_logs "
            "WHERE personality_notes IS NOT NULL AND personality_notes != ''"
        )
        legacy_rows = await cursor.fetchall()
        await cursor.close()

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for user_id, notes in legacy_rows:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM user_memories WHERE user_id = ?", (user_id,)
            )
            count = (await cursor.fetchone())[0]
            await cursor.close()
            if count > 0:
                continue
            await db.execute(
                "INSERT INTO user_memories (user_id, category, content, created_at, updated_at) "
                "VALUES (?, 'trait', ?, ?, ?)",
                (user_id, notes.strip(), now, now)
            )

        await db.commit()

        # ---- FTS5 backfill for existing rows ----
        cursor = await db.execute("SELECT COUNT(*) FROM user_memories_fts")
        if (await cursor.fetchone())[0] == 0:
            await db.execute(
                "INSERT INTO user_memories_fts(rowid, content) SELECT id, content FROM user_memories"
            )
        await cursor.close()

        cursor = await db.execute("SELECT COUNT(*) FROM world_state_fts")
        if (await cursor.fetchone())[0] == 0:
            await db.execute(
                "INSERT INTO world_state_fts(rowid, key, value) SELECT rowid, key, value FROM world_state"
            )
        await cursor.close()

        await db.commit()

    await init_connection_pool()

async def delete_user_data(user_id: str) -> None:
    async with db_pool.get_connection() as db:
        await db.execute("DELETE FROM user_logs WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM user_memories WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM user_personality WHERE user_id = ?", (user_id,))
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

async def record_user_message(server_id: str, user_id: str, username: str) -> None:
    """Upsert the interaction count and user log for one message, in one
    transaction. SQLite handles Discord-bot message rates fine without
    batching or background flush loops."""
    interactions = interaction_cache.get(user_id, 0) + 1
    interaction_cache[user_id] = interactions
    now = datetime.datetime.now(datetime.timezone.utc)

    try:
        async with db_pool.get_connection() as db:
            await db.execute("""
                INSERT INTO server_interactions (server_id, user_id, count)
                VALUES (?, ?, 1)
                ON CONFLICT(server_id, user_id)
                DO UPDATE SET count = count + 1
            """, (server_id, user_id))
            await db.execute("""
                INSERT INTO user_logs (user_id, username, interactions, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    interactions = excluded.interactions,
                    last_seen = excluded.last_seen
            """, (user_id, username, interactions, now))
            await db.commit()
    except aiosqlite.Error as e:
        logger.error(f"Database error in record_user_message: {e}")

    invalidate_user_log_cache(user_id)

async def show_server_interactions_user(server_id: str, user_id: str) -> int:
    try:
        async with db_pool.get_connection() as db:
            cursor = await db.execute("SELECT count FROM server_interactions WHERE server_id=? AND user_id=?", (server_id, user_id))
            row = await cursor.fetchone()
            count = row[0] if row else 0
            return count
    except aiosqlite.Error as e:
        logger.error(f"Database error in show_server_interactions_user: {e}")

async def show_server_interactions_leaderboard(server_id: str, limit: int = 10) -> list:
    try:
        async with db_pool.get_connection() as db:
            cursor = await db.execute(
                "SELECT user_id, count FROM server_interactions WHERE server_id=? ORDER BY count DESC LIMIT ?",
                (server_id, limit)
            )
            top_users = await cursor.fetchall()
            return top_users
    except aiosqlite.Error as e:
        logger.error(f"Database error in show_server_interactions_leaderboard: {e}")

# ============================================================================
# USER LOGS
# ============================================================================

async def flush_pending_notes_periodically():
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
                if notes:
                    await _parse_and_store_facts(user_id, notes)
                    logger.info(f"[Flushed Pending Notes] {username}")
                else:
                    await pending_notes_queue.put(pending_item)
                    logger.debug(f"[Notes Flush Failed] Requeued for {username}")
            else:
                notes = await _try_generate_notes(user_id, username, history)
                if notes:
                    logger.info(f"[Flushed Pending Notes] {username}")
                else:
                    await pending_notes_queue.put(pending_item)
                    logger.debug(f"[Notes Flush Failed] Requeued for {username}")
                
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.exception(f"[Notes Flush Error] {e}")

async def _try_generate_notes(user_id: str, username: str, history: list) -> str | None:
    """Generate structured per-category facts and store them as user_memories rows.

    Returns the rebuilt personality_notes blob, or None if the model is unreachable
    or there are too few messages to analyse.
    """
    user_texts = [
        h["content"] for h in history
        if h.get("role") == "user" and h.get("name") == username
    ]

    if len(user_texts) < 3:
        return None

    prompt = (
        f"Analyze {username}'s chat messages and extract 3-5 distinct facts.\n"
        f"{FACT_EXTRACTION_INSTRUCTIONS}\n\n"
        f"Messages from {username}:\n"
        + "\n".join(user_texts[-15:])
    )

    try:
        response = await chat_completion([{"role": "system", "content": prompt}])
        if not response or not response.strip():
            return None
        await _parse_and_store_facts(user_id, response)
        logger.debug(f"Generated structured notes for {user_id}.")
        # Return the rebuilt blob so callers that expect a string still work
        log = await get_user_log(user_id)
        return log[4] if log else None
    except Exception:
        logger.debug(f"[Notes Generation Failed - Model Unreachable] {user_id}")
        return None

async def _try_update_notes(username: str, history: list, old_notes: str) -> str | None:
    """Ask the model for NEW facts only (incremental update).

    Returns the raw model response (to be parsed by the caller), or None if
    the model is unreachable or nothing new was found.
    """
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
        f"Existing facts about {username}: {old_notes}\n\n"
        f"Recent messages from {username}:\n{recent}\n\n"
        "List only NEW facts not already covered above.\n"
        f"{FACT_EXTRACTION_INSTRUCTIONS}\n"
        "If nothing new, reply with 'no changes'."
    )

    try:
        response = await chat_completion([{"role": "system", "content": prompt}])
        cleaned = response.strip()
        if cleaned.lower() in ["", "no changes", "none"]:
            return None
        return cleaned
    except Exception:
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

async def update_personality_notes_with_username(user_id: str, username: str, notes: str) -> None:

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

async def maybe_queue_notes_update(user_id: str, username: str, history: list, interactions: int) -> None:
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

        # Store each new fact as a structured user_memory row
        await _parse_and_store_facts(user_id, notes)
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

    logger.info(f"[Cache Loaded] {len(interaction_cache)} users restored from DB")

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

async def clear_criminal_record(user_id: str, server_id: str) -> None:
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
# RAG HELPERS
# ============================================================================

def _fts_escape(query: str) -> str:
    """Strip FTS5 operator characters so user messages are safe to pass to MATCH."""
    cleaned = re.sub(r'[^\w\s]', ' ', query).strip()
    return cleaned if cleaned else '*'

async def add_user_memory(user_id: str, category: str, content: str, importance: int = 3) -> None:
    """Store a single structured fact about a user and keep the blob in sync."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with db_pool.get_connection() as db:
        await db.execute(
            "INSERT INTO user_memories (user_id, category, content, importance, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, category, content.strip(), clamp_importance(importance), now, now)
        )
        await db.commit()
    await _sync_personality_notes_blob(user_id)

async def list_user_memories(user_id: str) -> list[dict]:
    """Return all stored memories for a user, newest first."""
    async with db_pool.get_connection() as db:
        cursor = await db.execute(
            "SELECT id, category, content, importance, created_at "
            "FROM user_memories WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        await cursor.close()
    return [
        {"id": r[0], "category": r[1], "content": r[2], "importance": r[3], "created_at": r[4]}
        for r in rows
    ]

async def delete_user_memory(user_id: str, memory_id: int) -> bool:
    """Delete a single memory. Returns False when it doesn't belong to the user."""
    async with db_pool.get_connection() as db:
        cursor = await db.execute(
            "DELETE FROM user_memories WHERE id = ? AND user_id = ?",
            (memory_id, user_id)
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        await cursor.close()
    if deleted:
        await _sync_personality_notes_blob(user_id)
    return deleted

async def delete_all_user_memories(user_id: str) -> int:
    """Delete every memory for a user (also clears the denormalized blob)."""
    async with db_pool.get_connection() as db:
        cursor = await db.execute("DELETE FROM user_memories WHERE user_id = ?", (user_id,))
        await db.execute(
            "UPDATE user_logs SET personality_notes = NULL WHERE user_id = ?", (user_id,)
        )
        await db.commit()
        deleted = cursor.rowcount
        await cursor.close()
    invalidate_user_log_cache(user_id)
    return deleted

async def _sync_personality_notes_blob(user_id: str) -> None:
    """Rebuild user_logs.personality_notes from all user_memories rows.

    Keeps every consumer of log[4] working without modification.
    """
    async with db_pool.get_connection() as db:
        cursor = await db.execute(
            "SELECT category, content FROM user_memories WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return

        blob = "; ".join(f"[{row[0]}] {row[1]}" for row in rows)
        await db.execute(
            "UPDATE user_logs SET personality_notes = ? WHERE user_id = ?",
            (blob, user_id)
        )
        await db.commit()

    invalidate_user_log_cache(user_id)

async def _parse_and_store_facts(user_id: str, raw_text: str) -> None:
    """Parse LLM-generated [category|importance] fact lines and store each as a user_memory row."""
    for fact in parse_fact_lines(raw_text):
        await add_user_memory(user_id, fact["category"], fact["content"], fact["importance"])

# ============================================================================
# WORLD MEMORY SYSTEM
# ============================================================================

async def add_world_fact(server_id: str, key: str, value: str) -> bool:
    async with db_pool.get_connection() as db:
        # Check current count first
        cursor = await db.execute("SELECT COUNT(*) FROM world_state WHERE server_id = ?", (server_id,))
        count = (await cursor.fetchone())[0]
        await cursor.close()

        # Allow updates to existing keys, but prevent new ones if full
        if count >= MAX_WORLD_FACTS:
            # Check if we are updating an existing key
            cursor = await db.execute("SELECT 1 FROM world_state WHERE server_id = ? AND key = ?", (server_id, key))
            exists = await cursor.fetchone()
            await cursor.close()
            
            if not exists:
                return False  # Reject new entry

        await db.execute("""
            INSERT INTO world_state (server_id, key, value, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(server_id, key) DO UPDATE SET
                value = excluded.value,
                last_updated = excluded.last_updated
        """, (server_id, key, value, datetime.datetime.now(datetime.timezone.utc)))
        await db.commit()
        return True

async def get_world_context(server_id: str, server_name: str = "Unknown", owner_name: str = "Unknown") -> str:    
    async with db_pool.get_connection() as db:
        async with db.execute("""
            SELECT key, value 
            FROM world_state 
            WHERE server_id = ?
            ORDER BY key ASC
        """, (server_id,)) as cursor:
            facts = []
            async for row in cursor:
                key = row[0].replace("_", " ").title()
                value = row[1]
                facts.append(f"• **{key}**: {value}")
    
    # Always return the header, even if no custom facts exist
    header = (
        f"🌍 **Current World Context**\n"
        f"• **Location**: {server_name}\n"
        f"• **Owner/Ruler**: {owner_name}"
    )
    
    if not facts:
        return header
    
    return header + "\n" + "\n".join(facts)

async def delete_world_entry(server_id: str, key: str) -> None:
    async with db_pool.get_connection() as db:
        await db.execute(
            "DELETE FROM world_state WHERE server_id = ? AND key = ?",
            (server_id, key)
        )
        await db.commit()

async def delete_world_context(server_id: str) -> None:
    async with db_pool.get_connection() as db:
        await db.execute("DELETE FROM world_state WHERE server_id = ?", (server_id,))
        await db.commit()

async def list_world_facts(server_id: str) -> list:    
    async with db_pool.get_connection() as db:
        async with db.execute("""
            SELECT key, value, last_updated 
            FROM world_state 
            WHERE server_id = ?
            ORDER BY key ASC
        """, (server_id,)) as cursor:
            return [
                {"key": row[0], "value": row[1], "updated": row[2]}
                async for row in cursor
            ]

async def manual_world_update(server_id: str, key: str, value: str) -> bool:
    key_clean = key.lower().replace(" ", "_")
    return await add_world_fact(server_id, key_clean, value)

# ============================================================================
# RAG RETRIEVAL
# ============================================================================

async def get_relevant_user_memories(
    user_id: str, query: str, limit: int = 3
) -> list[str]:
    """Return the most relevant user memory facts for the given query via FTS5 BM25.

    Falls back to the most-recent rows when the query is empty or FTS fails.
    """
    fts_query = build_fts_query(query)
    if fts_query:
        try:
            async with db_pool.get_connection() as db:
                # Over-fetch by relevance, then re-rank blending BM25,
                # importance, and recency (see memory_service.rerank_memories)
                cursor = await db.execute("""
                    SELECT um.content, bm25(user_memories_fts) AS bm25,
                           um.importance, um.created_at
                    FROM user_memories_fts
                    JOIN user_memories um ON user_memories_fts.rowid = um.id
                    WHERE user_memories_fts MATCH ?
                      AND um.user_id = ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, user_id, limit * 3))
                rows = await cursor.fetchall()
                await cursor.close()
            if rows:
                candidates = [
                    {"content": r[0], "bm25": r[1], "importance": r[2], "created_at": r[3]}
                    for r in rows
                ]
                return [m["content"] for m in rerank_memories(candidates, limit=limit)]
        except Exception as e:
            logger.error(f"[RAG] user_memories FTS query failed for {user_id}: {e}")

    # Fallback: return most-recent memories regardless of relevance
    try:
        async with db_pool.get_connection() as db:
            cursor = await db.execute(
                "SELECT content FROM user_memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"[RAG] user_memories fallback failed for {user_id}: {e}")
        return []

async def get_relevant_world_facts(
    server_id: str, query: str, limit: int = 5
) -> list[dict]:
    """Return the most relevant world_state facts for the given query via FTS5 BM25.

    Falls back to all facts (original behaviour) on empty query or FTS failure.
    """
    fts_query = build_fts_query(query)
    if fts_query:
        try:
            async with db_pool.get_connection() as db:
                cursor = await db.execute("""
                    SELECT ws.key, ws.value
                    FROM world_state_fts
                    JOIN world_state ws ON world_state_fts.rowid = ws.rowid
                    WHERE world_state_fts MATCH ?
                      AND ws.server_id = ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, server_id, limit))
                rows = await cursor.fetchall()
                await cursor.close()
            if rows:
                return [{"key": row[0], "value": row[1]} for row in rows]
        except Exception as e:
            logger.error(f"[RAG] world_state FTS query failed for {server_id}: {e}")

    # Fallback: return all facts (preserves original behaviour)
    return await list_world_facts(server_id)

async def store_channel_memory(
    server_id: str,
    channel_id: str,
    summary: str,
    participants: list[str]
) -> None:
    """Persist a summarised memory of a significant channel exchange."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with db_pool.get_connection() as db:
        # Enforce cap — delete oldest entry if at limit
        cursor = await db.execute(
            "SELECT COUNT(*) FROM channel_memories WHERE server_id = ? AND channel_id = ?",
            (server_id, channel_id)
        )
        count = (await cursor.fetchone())[0]
        await cursor.close()

        if count >= MAX_CHANNEL_MEMORIES:
            await db.execute("""
                DELETE FROM channel_memories WHERE id = (
                    SELECT id FROM channel_memories
                    WHERE server_id = ? AND channel_id = ?
                    ORDER BY created_at ASC LIMIT 1
                )
            """, (server_id, channel_id))

        await db.execute("""
            INSERT INTO channel_memories (server_id, channel_id, summary, participants, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (server_id, channel_id, summary.strip(), json.dumps(participants), now))
        await db.commit()

async def get_relevant_channel_memories(
    server_id: str,
    channel_id: str,
    query: str,
    limit: int = 3
) -> list[str]:
    """Return the most relevant channel memory summaries for the given query via FTS5 BM25."""
    fts_query = build_fts_query(query)
    if not fts_query:
        return []
    try:
        async with db_pool.get_connection() as db:
            cursor = await db.execute("""
                SELECT cm.summary
                FROM channel_memories_fts
                JOIN channel_memories cm ON channel_memories_fts.rowid = cm.id
                WHERE channel_memories_fts MATCH ?
                  AND cm.server_id = ?
                  AND cm.channel_id = ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, server_id, channel_id, limit))
            rows = await cursor.fetchall()
            await cursor.close()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"[RAG] channel_memories FTS query failed for {server_id}/{channel_id}: {e}")
        return []
