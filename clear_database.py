# Script to clear all data from the database while keeping the schema

from database import engine, Base
from models import *  # Import all models to ensure tables are known
from sqlalchemy.orm import sessionmaker

# Create all tables (in case they don't exist)
Base.metadata.create_all(bind=engine)

# Create a session
Session = sessionmaker(bind=engine)
session = Session()

try:
    # Delete all data from all tables in correct order (reverse of dependencies)
    session.query(PushLog).delete()
    session.query(Device).delete()
    session.query(BaselinePEFR).delete()
    session.query(PEFRRecord).delete()
    session.query(Symptom).delete()
    session.query(MedicationStatusHistory).delete()
    session.query(Medication).delete()
    session.query(EmergencyContact).delete()
    session.query(Reminder).delete()
    session.query(Notification).delete()
    session.query(AuditLog).delete()
    session.query(AlertLog).delete()
    session.query(EmailLog).delete()
    session.query(DoctorPatient).delete()
    session.query(User).delete()

    # Commit the changes
    session.commit()
    print("All previous data has been deleted. Database is now fresh.")

except Exception as e:
    session.rollback()
    print(f"Error clearing database: {e}")

finally:
    session.close()