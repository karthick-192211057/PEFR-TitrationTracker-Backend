# asthma-backend/schemas.py

from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from app.models import UserRole

# --- Config for all schemas ---
class ConfigBase:
    from_attributes = True


# ------------------------------------------------------------
# MEDICATION SCHEMAS (UPDATED)
# ------------------------------------------------------------

class MedicationBase(BaseModel):
    name: str
    dose: Optional[str] = None
    schedule: Optional[str] = None
    start_date: Optional[datetime] = None
    days: Optional[int] = None
    cure_probability: Optional[float] = None
    doses_remaining: Optional[int] = None
    source: Optional[str] = None
    prescribed_by: Optional[int] = None


class MedicationCreate(MedicationBase):
    pass


class MedicationUpdate(BaseModel):
    name: Optional[str] = None
    dose: Optional[str] = None
    schedule: Optional[str] = None
    start_date: Optional[datetime] = None
    days: Optional[int] = None
    cure_probability: Optional[float] = None
    doses_remaining: Optional[int] = None


class MedicationTake(BaseModel):
    doses: Optional[int] = 1
    notes: Optional[str] = None


class Medication(MedicationBase):
    id: int
    owner_id: int
    taken_status: Optional[str] = "Not Updated"
    start_date: Optional[datetime] = None
    days: Optional[int] = None
    cure_probability: Optional[float] = None
    doses_remaining: Optional[int] = None

    class Config(ConfigBase):
        pass


class MedicationStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class MedicationStatusHistory(BaseModel):
    id: int
    medication_id: int
    status: str
    notes: Optional[str] = None
    changed_at: datetime
    changed_by_user_id: Optional[int] = None

    class Config(ConfigBase):
        pass


class MedicationWithHistory(Medication):
    status_history: List[MedicationStatusHistory] = []


# ------------------------------------------------------------
# EMERGENCY CONTACT SCHEMAS
# ------------------------------------------------------------

class EmergencyContactBase(BaseModel):
    name: str
    phone_number: str
    contact_relationship: Optional[str] = None


class EmergencyContactCreate(EmergencyContactBase):
    pass


class EmergencyContact(EmergencyContactBase):
    id: int
    owner_id: int

    class Config(ConfigBase):
        pass


# ------------------------------------------------------------
# REMINDER SCHEMAS
# ------------------------------------------------------------

class ReminderBase(BaseModel):
    reminder_type: str
    time: str
    frequency: str


class ReminderCreate(ReminderBase):
    pass


class Reminder(ReminderBase):
    id: int
    compliance_count: int
    missed_count: int
    owner_id: int

    class Config(ConfigBase):
        pass


# ------------------------------------------------------------
# NOTIFICATION SCHEMAS
# ------------------------------------------------------------

class NotificationBase(BaseModel):
    message: str
    link: Optional[str] = None


class NotificationCreate(NotificationBase):
    pass


class Notification(NotificationBase):
    id: int
    owner_id: int
    created_at: datetime
    read: bool

    class Config(ConfigBase):
        pass


class EmailLog(BaseModel):
    id: int
    recipient: str
    subject: Optional[str] = None
    purpose: Optional[str] = None
    success: bool
    error: Optional[str] = None
    created_at: datetime

    class Config(ConfigBase):
        pass


# ------------------------------------------------------------
# PEFR SCHEMAS
# ------------------------------------------------------------

class BaselinePEFRBase(BaseModel):
    baseline_value: int


class BaselinePEFRCreate(BaselinePEFRBase):
    pass


class BaselinePEFR(BaselinePEFRBase):
    id: int
    owner_id: int

    class Config(ConfigBase):
        pass


class PEFRRecordCreate(BaseModel):
    pefr_value: int
    source: Optional[str] = "manual"


class PEFRRecord(BaseModel):
    id: int
    pefr_value: int
    zone: str
    recorded_at: datetime
    owner_id: int
    percentage: Optional[float] = None
    trend: Optional[str] = None
    source: Optional[str] = None

    class Config(ConfigBase):
        pass


class PEFRRecordResponse(BaseModel):
    zone: str
    guidance: str
    record: PEFRRecord
    percentage: Optional[float] = None
    trend: Optional[str] = None


# ------------------------------------------------------------
# SYMPTOM SCHEMAS
# ------------------------------------------------------------

class SymptomCreate(BaseModel):
    wheeze_rating: Optional[int] = None
    cough_rating: Optional[int] = None
    dust_exposure: Optional[bool] = False
    smoke_exposure: Optional[bool] = False
    dyspnea_rating: Optional[int] = None
    night_symptoms_rating: Optional[int] = None
    severity: Optional[str] = None
    onset_at: Optional[datetime] = None
    duration: Optional[int] = None
    suspected_trigger: Optional[str] = None


class Symptom(SymptomCreate):
    id: int
    recorded_at: datetime
    owner_id: int

    class Config(ConfigBase):
        pass


# ------------------------------------------------------------
# USER & AUTH SCHEMAS
# ------------------------------------------------------------

class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: UserRole


class UserCreate(UserBase):
    password: str
    age: Optional[int] = None
    height: Optional[int] = None
    gender: Optional[str] = None
    contact_number: Optional[str] = None
    address: Optional[str] = None


class User(UserBase):
    id: int
    age: Optional[int] = None
    height: Optional[int] = None
    gender: Optional[str] = None
    contact_number: Optional[str] = None
    address: Optional[str] = None

    medications: List[Medication] = []
    emergency_contacts: List[EmergencyContact] = []
    reminders: List[Reminder] = []
    baseline: Optional[BaselinePEFR] = None

    latest_pefr_record: Optional[PEFRRecord] = None
    latest_symptom: Optional[Symptom] = None

    class Config(ConfigBase):
        pass


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user_role: UserRole


class TokenData(BaseModel):
    email: Optional[str] = None


# ------------------------------------------------------------
# DOCTOR-PATIENT LINK SCHEMAS
# ------------------------------------------------------------

class DoctorPatientLinkCreate(BaseModel):
    doctor_email: EmailStr


class DoctorPatientLink(BaseModel):
    id: int
    doctor_id: int
    patient_id: int

    class Config(ConfigBase):
        pass


# ------------------------------------------------------------
# AUTH / OTP REQUEST SCHEMAS
# ------------------------------------------------------------


class SignupOtpRequest(BaseModel):
    email: EmailStr
    otp: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str


# -----------------------------
# Machine Learning Schemas
# -----------------------------
class MLInput(BaseModel):
    age: Optional[int] = None
    pefr_value: int
    wheeze_rating: Optional[int] = 0
    cough_rating: Optional[int] = 0
    dust_exposure: Optional[bool] = False
    smoke_exposure: Optional[bool] = False


class MLPrediction(BaseModel):
    recommended_medicine: str
    recommended_days: int
    predicted_cure_probability: float

    class Config(ConfigBase):
        pass
