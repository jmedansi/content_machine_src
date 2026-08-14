import sqlite3
import json
from pathlib import Path

def init_db(db_path: str = 'content_machine.db'):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Accounts table
    c.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            page_id TEXT,
            name TEXT,
            meta TEXT,  -- JSON
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_accounts_platform ON accounts(platform)')
    # Contents table
    c.execute('''
        CREATE TABLE IF NOT EXISTS contents (
            id TEXT PRIMARY KEY,
            account_id TEXT,
            platform TEXT,
            folder TEXT,
            file_path TEXT,
            meta TEXT,  -- JSON
            status TEXT CHECK(status IN ('pending','written','published')) DEFAULT 'pending',
            checksum TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_contents_account_status ON contents(account_id, status)')
    conn.commit()
    return conn

def insert_account(conn, account_id: str, platform: str, page_id: str = None, name: str = None, meta: dict = None):
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO accounts (id, platform, page_id, name, meta) VALUES (?, ?, ?, ?, ?)',
              (account_id, platform, page_id, name, json.dumps(meta) if meta else None))
    conn.commit()

def insert_content(conn, content_id: str, account_id: str, platform: str, folder: str, file_path: str, meta: dict, status: str = 'pending'):
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO contents (id, account_id, platform, folder, file_path, meta, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (content_id, account_id, platform, folder, file_path, json.dumps(meta), status))
    conn.commit()

def update_content_status(conn, content_id: str, status: str, checksum: str = None):
    c = conn.cursor()
    c.execute('UPDATE contents SET status = ?, checksum = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
              (status, checksum, content_id))
    conn.commit()

def get_accounts(conn):
    c = conn.cursor()
    c.execute('SELECT id, platform, page_id, name, meta FROM accounts')
    return c.fetchall()

def get_contents_by_account(conn, account_id: str):
    c = conn.cursor()
    c.execute('SELECT id, folder, file_path, meta, status FROM contents WHERE account_id = ?', (account_id,))
    return c.fetchall()