import sqlite3
import os

db_path = "pefrtitrationtracker.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("=== USERS IN DATABASE ===")
cur.execute("SELECT id, email, name, role, hashed_password FROM users")
users = cur.fetchall()
for user in users:
    print(f"ID: {user[0]}")
    print(f"  Email: {user[1]}")
    print(f"  Name: {user[2]}")
    print(f"  Role: {user[3]}")
    print(f"  Hashed Password: {user[4][:50]}...")
    print()

# Check if doctor_patient_map exists
print("=== DOCTOR-PATIENT LINKS ===")
try:
    cur.execute("SELECT * FROM doctor_patient_map")
    links = cur.fetchall()
    for link in links:
        print(f"Patient ID {link[1]} linked to Doctor ID {link[2]}")
except Exception as e:
    print(f"Error: {e}")

conn.close()
