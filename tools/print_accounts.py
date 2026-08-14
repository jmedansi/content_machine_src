import sqlite3, json, sys

DB_PATHS = [
    'data/leads_station.db',
    'machines/facebook_machine/data/leads_station.db',
    'machines/linkedin_machine/data/leads_station.db',
    'machines/twitter_machine/data/leads_station/data/leads_station.db',
]

def print_accounts(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute('SELECT id, platform, name, credentials, status, created_at FROM accounts')
        rows = cur.fetchall()
        print('\nDB:', db_path)
        if not rows:
            print('  (no accounts)')
        for r in rows:
            id_, plat, name, creds, status, created = r
            try:
                creds = json.loads(creds) if creds else {}
            except:
                pass
            print(' ', id_, plat, name, status, creds)
        conn.close()
    except Exception as e:
        print('\nDB:', db_path, ' error:', e)

if __name__ == '__main__':
    paths = DB_PATHS
    if len(sys.argv) > 1:
        paths = sys.argv[1:]
    for p in paths:
        print_accounts(p)