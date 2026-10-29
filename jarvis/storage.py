import sqlite3
from datetime import datetime, timezone
from jarvis.paths import STATE


def connection():
    db = sqlite3.connect(STATE / "history.sqlite")
    db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, role TEXT NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL)")
    return db


def add_message(role: str, text: str):
    with connection() as db:
        db.execute("INSERT INTO messages(role,text,created) VALUES (?,?,?)", (role, text, datetime.now(timezone.utc).isoformat()))


def history(limit=100):
    with connection() as db:
        rows = db.execute("SELECT role,text,created FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"role": role, "text": text, "created": created} for role, text, created in reversed(rows)]


def clear():
    with connection() as db:
        db.execute("DELETE FROM messages")
