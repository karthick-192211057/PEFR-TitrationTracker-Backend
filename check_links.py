import sqlite3

conn = sqlite3.connect('pefrtitrationtracker.db')
cur = conn.cursor()
print('doctor_patient_map:')
for row in cur.execute('SELECT id, patient_id, doctor_id FROM doctor_patient_map'):
    print(row)
conn.close()
