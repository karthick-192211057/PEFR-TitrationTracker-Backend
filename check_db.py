from app import database
import os
import sqlite3

print(f'Database URL: {database.SQLALCHEMY_DATABASE_URL}')
print(f'Current directory: {os.getcwd()}')

# Find the database file
db_files = [
    'pefrtitrationtracker.db',
    './pefrtitrationtracker.db',
    '../pefrtitrationtracker.db',
    'asthma-backend/pefrtitrationtracker.db',
]

print('\nSearching for database files:')
for db_file in db_files:
    exists = os.path.exists(db_file)
    print(f'  {db_file}: {exists}')
    if exists:
        try:
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            print(f'    -> Contains {count} users')
            conn.close()
        except Exception as e:
            print(f'    -> Error reading: {e}')

# Also check env variable
print(f'\nDATABASE_URL env: {os.getenv("DATABASE_URL", "Not set")}')
