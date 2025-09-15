import os
import aiosqlite

DB_PATH =  "data/yaps.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

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
        await db.commit()

async def increment_yap(server_id: str, user_id: str):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO yaps (server_id, user_id, count)
                VALUES (?, ?, 1)
                ON CONFLICT(server_id, user_id)
                DO UPDATE SET count = count + 1
            """, (server_id, user_id))
            await db.commit()
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