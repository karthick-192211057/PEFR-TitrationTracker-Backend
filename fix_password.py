import sqlite3
from passlib.context import CryptContext

# Connect to database
conn = sqlite3.connect("pefrtitrationtracker.db")
cur = conn.cursor()

# Check current password for karthicksaravanan0703@gmail.com
cur.execute("SELECT id, email, role, hashed_password FROM users WHERE email = ?", 
            ("karthicksaravanan0703@gmail.com",))
user = cur.fetchone()

if user:
    print(f"Email: {user[1]}")
    print(f"Role: {user[2]}")
    print(f"Current hash: {user[3][:50]}...")
    
    # Update password to TestPassword123!
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    new_password = "TestPassword123!"
    hashed_password = pwd_context.hash(new_password)
    
    print(f"\nUpdating password to: {new_password}")
    cur.execute("UPDATE users SET hashed_password = ? WHERE email = ?", 
                (hashed_password, "karthicksaravanan0703@gmail.com"))
    conn.commit()
    
    # Verify
    cur.execute("SELECT hashed_password FROM users WHERE email = ?", 
                ("karthicksaravanan0703@gmail.com",))
    new_hash = cur.fetchone()[0]
    print(f"New hash: {new_hash[:50]}...")
    
    # Test verification
    pwd_context_test = CryptContext(schemes=["bcrypt"], deprecated="auto")
    is_valid = pwd_context_test.verify("TestPassword123!", new_hash)
    print(f"\nPassword verification test: {'PASS' if is_valid else 'FAIL'}")
else:
    print("User not found!")

conn.close()
