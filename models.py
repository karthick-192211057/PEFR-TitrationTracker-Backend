# asthma-backend/models.py

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base
import datetime
import enum

class UserRole(str, enum.Enum):
    PATIENT = "Patient"
    DOCTOR = "Doctor"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)

    # --- ADDED/UPDATED FIELDS ---
    age = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)  # in cm
    gender = Column(String, nullable=True)
    contact_number = Column(String, nullable=True)
    address = Column(String, nullable=True)
    # FCM device token for push notifications
    fcm_token = Column(String, nullable=True)

    # Relationships
    baseline = relationship("BaselinePEFR", back_populates="owner", uselist=False)
    pefr_records = relationship("PEFRRecord", back_populates="owner")
    symptoms = relationship("Symptom", back_populates="owner")

    # --- NEW RELATIONSHIPS ---
    medications = relationship("Medication", back_populates="owner")
    emergency_contacts = relationship("EmergencyContact", back_populates="owner")
    reminders = relationship("Reminder", back_populates="owner")
    audit_logs = relationship("AuditLog", back_populates="user")
    alert_logs = relationship("AlertLog", back_populates="user")
    # Notifications for the user
    notifications = relationship("Notification", back_populates="owner")

    # NEW: Medication status history linkage
    medication_status_changes = relationship("MedicationStatusHistory", back_populates="changed_by_user")


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, nullable=False, unique=True)
    platform = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow)
    active = Column(Boolean, default=True)


class PushLog(Base):
    __tablename__ = "push_logs"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    token = Column(String, nullable=True)
    success = Column(Boolean, default=False)
    response = Column(String, nullable=True)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    # no relationships here; this table only logs push attempts


class BaselinePEFR(Base):
    __tablename__ = "baseline_pefr"

    id = Column(Integer, primary_key=True, index=True)
    baseline_value = Column(Integer, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="baseline")


class PEFRRecord(Base):
    __tablename__ = "pefr_records"

    id = Column(Integer, primary_key=True, index=True)
    pefr_value = Column(Integer, nullable=False)
    zone = Column(String, nullable=False)
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))

    # --- ADDED/UPDATED FIELDS ---
    percentage = Column(Float, nullable=True)
    trend = Column(String, nullable=True)
    source = Column(String, default="manual")

    owner = relationship("User", back_populates="pefr_records")


class Symptom(Base):
    __tablename__ = "symptoms"

    id = Column(Integer, primary_key=True, index=True)
    wheeze_rating = Column(Integer)
    cough_rating = Column(Integer)
    dust_exposure = Column(Boolean, default=False)
    smoke_exposure = Column(Boolean, default=False)
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))

    # --- ADDED/UPDATED FIELDS ---
    dyspnea_rating = Column(Integer, nullable=True)
    night_symptoms_rating = Column(Integer, nullable=True)
    severity = Column(String, nullable=True)
    onset_at = Column(DateTime, nullable=True)
    duration = Column(Integer, nullable=True)
    suspected_trigger = Column(String, nullable=True)

    owner = relationship("User", back_populates="symptoms")


class DoctorPatient(Base):
    __tablename__ = "doctor_patient_map"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"))
    patient_id = Column(Integer, ForeignKey("users.id"))


# -------------------------------------------------------------------
# ----------------------  NEW MEDICATION CHANGES  --------------------
# -------------------------------------------------------------------

class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    dose = Column(String, nullable=True)
    schedule = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="medications")

    # NEW FIELD (default ensures backward compatibility)
    taken_status = Column(String, default="Not Updated")

    # Persisted medication metadata
    start_date = Column(DateTime, nullable=True)
    days = Column(Integer, nullable=True)
    cure_probability = Column(Float, nullable=True)
    doses_remaining = Column(Integer, nullable=True)
    # Source of medication: 'doctor', 'ai', or 'patient'
    source = Column(String, nullable=True, default="patient")
    # If prescribed by a doctor, store their user id
    prescribed_by = Column(Integer, nullable=True)

    # NEW RELATIONSHIP
    status_history = relationship("MedicationStatusHistory", back_populates="medication")


class MedicationStatusHistory(Base):
    __tablename__ = "medication_status_history"

    id = Column(Integer, primary_key=True, index=True)
    medication_id = Column(Integer, ForeignKey("medications.id"))
    status = Column(String, nullable=False)  # Taken / Not Taken / Not Updated
    notes = Column(String, nullable=True)
    changed_at = Column(DateTime, default=datetime.datetime.utcnow)

    changed_by_user_id = Column(Integer, ForeignKey("users.id"))

    # relationships
    medication = relationship("Medication", back_populates="status_history")
    changed_by_user = relationship("User", back_populates="medication_status_changes")


# -------------------------------------------------------------------
# ---------------------- OTHER EXISTING TABLES ----------------------
# -------------------------------------------------------------------

class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    contact_relationship = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="emergency_contacts")


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    reminder_type = Column(String, nullable=False)
    time = Column(String, nullable=False)
    frequency = Column(String, nullable=False)
    compliance_count = Column(Integer, default=0)
    missed_count = Column(Integer, default=0)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="reminders")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(String, nullable=False)
    link = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    read = Column(Boolean, default=False)

    owner = relationship("User", back_populates="notifications")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String, nullable=False)
    details = Column(String, nullable=True)

    user = relationship("User", back_populates="audit_logs")


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    alert_type = Column(String, nullable=False)
    resolved = Column(Boolean, default=False)

    user = relationship("User", back_populates="alert_logs")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    recipient = Column(String, nullable=False)
    subject = Column(String, nullable=True)
    purpose = Column(String, nullable=True)
    success = Column(Boolean, default=False)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

