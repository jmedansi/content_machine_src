import sqlite3
paths=['data/leads_station.db','machines/facebook_machine/data/leads_station.db','machines/linkedin_machine/data/leads_station.db','machines/twitter_machine/data/leads_station.db']
for p in paths:
    try:
        conn=sqlite3.connect(p)
        cur=conn.cursor()
        cur.execute("SELECT id,platform,name,status FROM accounts")
        rows=cur.fetchall()
        print('\nDB:',p)
        if not rows:
            print('  (no accounts)')
        for r in rows[:10]:
            print(' ',r)
        conn.close()
    except Exception as e:
        print('\nDB:',p,' error:',e)
