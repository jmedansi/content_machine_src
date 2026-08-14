import sys
sys.path.append('.')
from dashboard_api_v2 import PLATFORM_DB
import sqlite3
from pathlib import Path

db_path = PLATFORM_DB.get('facebook')
if db_path and Path(db_path).exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.execute('PRAGMA table_info(posts)')
    columns = cursor.fetchall()
    print('Colonnes de la table posts:')
    for col in columns:
        print(f'  {col[1]} ({col[2]})')

    cursor = conn.execute('SELECT COUNT(*) FROM posts WHERE status="pending" AND account_id=1')
    count = cursor.fetchone()[0]
    print(f'\nPosts en attente pour compte 1: {count}')

    if count > 0:
        cursor = conn.execute('SELECT id, topic, persona, status, created_at FROM posts WHERE status="pending" AND account_id=1 ORDER BY created_at DESC LIMIT 5')
        posts = cursor.fetchall()
        for post in posts:
            print(f'  ID: {post[0]}, Topic: {post[1]}, Persona: {post[2]}, Status: {post[3]}, Created: {post[4]}')

    conn.close()
else:
    print('DB not found')