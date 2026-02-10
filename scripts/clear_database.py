# Script to clear all data from the database while keeping the schema

from app.database import engine, Base
from app import models
from sqlalchemy.orm import sessionmaker

# Create all tables (in case they don't exist)
Base.metadata.create_all(bind=engine)

# Create a session
Session = sessionmaker(bind=engine)
session = Session()

try:
    # Delete all data from all tables (reverse dependency order)
    session.query(models.PushLog).delete()
    session.query(models.Device).delete()
    session.query(models.BaselinePEFR).delete()
    session.query(models.PEFRRecord).delete()
    session.query(models.Symptom).delete()
    session.query(models.MedicationStatusHistory).delete()
    session.query(models.Medication).delete()
    session.query(models.EmergencyContact).delete()
    session.query(models.Reminder).delete()
    session.query(models.Notification).delete()
    session.query(models.AuditLog).delete()
    session.query(models.AlertLog).delete()
    session.query(models.EmailLog).delete()
    session.query(models.DoctorPatient).delete()
    session.query(models.User).delete()

    session.commit()
    print("✅ All previous data has been deleted. Database is now fresh.")

except Exception as e:
    session.rollback()
    print(f"❌ Error clearing database: {e}")

finally:
    session.close()
