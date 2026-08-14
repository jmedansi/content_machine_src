import sqlite3

conn = sqlite3.connect('d:/Content_Machine/machines/linkedin_machine/data/leads_station.db')
cursor = conn.execute("UPDATE posts SET status='pending' WHERE account_id=1 AND status='draft' AND published=0")
print('Updated rows:', cursor.rowcount)
conn.commit()

cursor = conn.execute("SELECT folder_name, status FROM posts WHERE account_id=1 ORDER BY id DESC LIMIT 5")
print('\nPosts LinkedIn account 1 après correction:')
for row in cursor.fetchall():
    print(f'{row[0]}: {row[1]}')

conn.close()