# task_tracker.py — Suivi des tâches en temps réel avec persistance SQLite
import sqlite3
import json
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "tasks.db"

def _init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            progress INTEGER DEFAULT 0,
            message TEXT,
            logs TEXT DEFAULT '[]',
            folder TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()

_init_db()


def create_task(task_type: str, folder: str = None, message: str = "") -> str:
    """Crée une nouvelle tâche et retourne son ID."""
    task_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute(
        "INSERT INTO tasks (id, type, status, progress, message, logs, folder, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_id, task_type, "pending", 0, message, "[]", folder, now, now)
    )
    conn.commit()
    conn.close()
    
    return task_id


def update_task(task_id: str, progress: int = None, status: str = None, message: str = None, log: str = None):
    """Met à jour une tâche existante."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    
    updates = []
    params = []
    
    if progress is not None:
        updates.append("progress = ?")
        params.append(progress)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if message is not None:
        updates.append("message = ?")
        params.append(message)
    if log is not None:
        cur = conn.execute("SELECT logs FROM tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if row:
            logs = json.loads(row[0]) if row[0] else []
            logs.append({"time": datetime.now().isoformat(), "message": log})
            updates.append("logs = ?")
            params.append(json.dumps(logs))
    
    if not updates:
        conn.close()
        return
    
    updates.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.append(task_id)
    
    conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", tuple(params))
    conn.commit()
    conn.close()


def get_task(task_id: str) -> Optional[dict]:
    """Récupère une tâche par son ID."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row[0],
            "type": row[1],
            "status": row[2],
            "progress": row[3],
            "message": row[4],
            "logs": json.loads(row[5]),
            "folder": row[6],
            "created_at": row[7],
            "updated_at": row[8]
        }
    return None


def get_active_tasks() -> list:
    """Récupère toutes les tâches actives (non terminées)."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.execute("SELECT * FROM tasks WHERE status NOT IN ('completed', 'failed') ORDER BY updated_at DESC")
    rows = cur.fetchall()
    conn.close()
    
    return [
        {
            "id": row[0],
            "type": row[1],
            "status": row[2],
            "progress": row[3],
            "message": row[4],
            "logs": json.loads(row[5]),
            "folder": row[6],
            "created_at": row[7],
            "updated_at": row[8]
        }
        for row in rows
    ]


def clear_old_tasks(days: int = 7):
    """Supprime les tâches anciennes (par défaut plus de 7 jours)."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute(f"DELETE FROM tasks WHERE updated_at < datetime('now', '-{days} days')")
    conn.commit()
    conn.close()