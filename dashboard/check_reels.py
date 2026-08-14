import sqlite3
from pathlib import Path

platforms = {'facebook': 'd:/Content_Machine/machines/facebook_machine/data/leads_station.db', 'linkedin': 'd:/Content_Machine/machines/linkedin_machine/data/leads_station.db'}

for platform, db_path in platforms.items():
    print(f'\n=== {platform.upper()} ===')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    cur = conn.execute('SELECT id, account_id, folder_name, status, published, has_reel, reel_filename, created_at FROM posts WHERE has_reel=1 ORDER BY id DESC LIMIT 5')
    rows = cur.fetchall()
    if rows:
        print('Recent posts with reels:')
        for r in rows:
            print(f'  {r["id"]} account={r["account_id"]} {r["folder_name"]} status={r["status"]} published={r["published"]} reel={r["reel_filename"]} created={r["created_at"]}')
    else:
        print('No posts with reels found')
    
    # Check all recent posts to see if any are reels
    cur = conn.execute('SELECT id, account_id, folder_name, status, published, has_reel, created_at FROM posts ORDER BY id DESC LIMIT 10')
    rows = cur.fetchall()
    print('\nAll recent posts:')
    for r in rows:
        has_r = 'Y' if r['has_reel'] else 'N'
        print(f'  {r["id"]} account={r["account_id"]} status={r["status"]} reel={has_r} {r["folder_name"]}')
    
    conn.close()
