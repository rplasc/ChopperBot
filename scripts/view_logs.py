import os
import asyncio
import aiosqlite
import json
import csv
from textwrap import shorten

DB_PATH = "data/analytics.db"


async def view_all_logs(limit: int = 50):
    """Show the latest chat logs (default: 50)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT timestamp, server_id, channel_id, username, role, content
            FROM chat_logs
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()

    print("\n=== Last {} Messages ===".format(limit))
    for ts, server, channel, user, role, content in reversed(rows):
        short_content = shorten(content, width=80, placeholder="...")
        print(f"[{ts}] ({server}/{channel}) {user} [{role}]: {short_content}")


async def view_user_logs(user_id: str, limit: int = 20):
    """Show logs for a specific user."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT timestamp, username, role, content
            FROM chat_logs
            WHERE user_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
        """, (user_id, limit))
        rows = await cursor.fetchall()

    print(f"\n=== Logs for user {user_id} ===")
    for ts, username, role, content in rows:
        print(f"[{ts}] {username} [{role}]: {content}")


async def top_users():
    """Show most active users by message count."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, username, COUNT(*) as message_count
            FROM chat_logs
            WHERE role = 'user'
            GROUP BY user_id, username
            ORDER BY message_count DESC
            LIMIT 10
        """)
        rows = await cursor.fetchall()

    print("\n=== Top 10 Active Users ===")
    for uid, uname, count in rows:
        print(f"{uname} ({uid}): {count} messages")

async def export_all_logs(file_path="exports/chat_logs.txt", limit: int = 100):
    """Export the latest chat logs into a plain text file."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT timestamp, server_id, channel_id, username, role, content
            FROM chat_logs
            ORDER BY timestamp ASC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        for ts, server, channel, user, role, content in rows:
            f.write(f"[{ts}] ({server}/{channel}) {user} [{role}]: {content}\n")

    print(f"✅ Exported {len(rows)} logs to {file_path}")

async def export_logs_csv(file_path="exports/chat_logs.csv", limit: int = 1000):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT timestamp, server_id, channel_id, user_id, username, role, content
            FROM chat_logs
            ORDER BY timestamp ASC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "server_id", "channel_id", "user_id", "username", "role", "content"])
        writer.writerows(rows)

    print(f"✅ Exported {len(rows)} logs to {file_path}")

async def export_logs_json(file_path="exports/chat_logs.json", limit: int = 1000):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT timestamp, server_id, channel_id, user_id, username, role, content
            FROM chat_logs
            ORDER BY timestamp ASC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()

    data = [
        {
            "timestamp": ts,
            "server_id": server,
            "channel_id": channel,
            "user_id": uid,
            "username": uname,
            "role": role,
            "content": content
        }
        for ts, server, channel, uid, uname, role, content in rows
    ]

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Exported {len(rows)} logs to {file_path}")

async def run():
    # Default export
    await export_all_logs()

if __name__ == "__main__":
    asyncio.run(run())
