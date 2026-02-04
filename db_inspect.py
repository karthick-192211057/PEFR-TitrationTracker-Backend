import sqlite3, os

db='asthma-backend/pefrtitrationtracker.db'
if not os.path.exists(db):
    print('DB not found at', db)
    raise SystemExit(1)
conn=sqlite3.connect(db)
cur=conn.cursor()
print('\n== devices ==')
try:
    for r in cur.execute('select id,owner_id,token,active,last_seen from devices'):
        print(r)
except Exception as e:
    print('devices table error', e)

print('\n== push_logs (recent 50) ==')
try:
    for r in cur.execute('select id,owner_id,token,success,response,error,created_at from push_logs order by created_at desc limit 50'):
        print(r)
except Exception as e:
    print('push_logs table error', e)

print('\n== notifications (recent 20) ==')
try:
    for r in cur.execute('select id,owner_id,message,link,created_at from notifications order by created_at desc limit 20'):
        print(r)
except Exception as e:
    print('notifications table error', e)

print('\n== medications with prescribed_by (recent 20) ==')
try:
    for r in cur.execute('select id,owner_id,name,prescribed_by,source from medications where prescribed_by is not null order by id desc limit 20'):
        print(r)
except Exception as e:
    print('medications table error', e)

conn.close()
