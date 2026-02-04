import sqlite3

db = 'c:/Users/karth/AndroidStudioProjects/AsthmaManagerApp/asthma-backend/pefrtitrationtracker.db'
conn = sqlite3.connect(db)
c = conn.cursor()
email = 'karthicksaravanan0703@gmail.com'
try:
    c.execute('SELECT id, email, name, role FROM users WHERE email = ?', (email,))
    rows = c.fetchall()
    print('EXACT_MATCH:', rows)
    c.execute('SELECT id, email, name, role FROM users WHERE lower(email) = ?', (email.lower(),))
    print('LOWER_MATCH:', c.fetchall())
    c.execute("SELECT id, email FROM users WHERE email LIKE '%' || ? || '%'", (email.split('@')[0],))
    print('LIKE_PART:', c.fetchall())
except Exception as e:
    print('ERR', e)
finally:
    conn.close()
