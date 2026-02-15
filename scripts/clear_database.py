# Script to clear all data from the database while keeping the schema

from app.database import engine, Base
from app import models
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

Session = sessionmaker(bind=engine)
session = Session()

try:
    # Disable foreign key checks (SQLite specific)
    session.execute(text("PRAGMA foreign_keys = OFF;"))

    # Delete in proper dependency-safe order
    session.query(models.PushLog).delete()
    session.query(models.Device).delete()
    session.query(models.MedicationStatusHistory).delete()
    session.query(models.Medication).delete()
    session.query(models.Notification).delete()
    session.query(models.Reminder).delete()
    session.query(models.EmergencyContact).delete()
    session.query(models.PEFRRecord).delete()
    session.query(models.Symptom).delete()
    session.query(models.BaselinePEFR).delete()
    session.query(models.DoctorPatient).delete()
    session.query(models.AuditLog).delete()
    session.query(models.AlertLog).delete()
    session.query(models.EmailLog).delete()
    session.query(models.User).delete()

    # Reset auto-increment counters (if table exists)
    try:
        session.execute(text("DELETE FROM sqlite_sequence;"))
    except:
        pass

    # Re-enable foreign keys
    session.execute(text("PRAGMA foreign_keys = ON;"))

    session.commit()
    print("✅ Database fully cleaned and ID counters reset.")

except Exception as e:
    session.rollback()
    print(f"❌ Error clearing database: {e}")

finally:
    session.close()