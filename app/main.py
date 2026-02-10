# asthma-backend/main.py
from fastapi import FastAPI, Depends, HTTPException, status, Query, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, text, inspect
from typing import List, Optional

import os
import datetime

from app import auth, database, models, schemas
from app.database import engine
from app.otp_service import (
    generate_otp,
    store_otp,
    verify_otp,
    clear_otp,
    send_otp_email
)

from ml.predictor import get_predictor
import app.firebase_messaging as firebase_messaging
from fastapi import BackgroundTasks

# Create all database tables on startup
app = FastAPI()

# Create all database tables on startup
models.Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def ensure_medication_columns():
    """Attempt to add medication metadata columns if they're missing (safe for dev SQLite)."""
    try:
        insp = inspect(engine)
        if 'medications' not in insp.get_table_names():
            # nothing to migrate if table doesn't exist yet
            return

        conn = engine.connect()
        res = conn.execute(text("PRAGMA table_info('medications')")).fetchall()
        existing_cols = [r[1] for r in res]
        additions = {
            'start_date': 'DATETIME',
            'days': 'INTEGER',
            'cure_probability': 'FLOAT',
            'doses_remaining': 'INTEGER',
            'source': 'TEXT',
            'prescribed_by': 'INTEGER'
        }
        for col, ddl in additions.items():
            if col not in existing_cols:
                try:
                    conn.execute(text(f"ALTER TABLE medications ADD COLUMN {col} {ddl}"))
                    print(f"Added column {col} to medications table")
                except Exception as e:
                    print(f"Could not add column {col}: {e}")
        conn.close()
    except Exception as e:
        print("Startup migration check failed:", e)


@app.on_event("startup")
def ensure_user_columns():
    """Ensure user table has FCM token column for push notifications."""
    try:
        insp = inspect(engine)
        if 'users' not in insp.get_table_names():
            return

        conn = engine.connect()
        res = conn.execute(text("PRAGMA table_info('users')")).fetchall()
        existing_cols = [r[1] for r in res]
        if 'fcm_token' not in existing_cols:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN fcm_token TEXT"))
                print("Added column fcm_token to users table")
            except Exception as e:
                print(f"Could not add column fcm_token: {e}")
        conn.close()
    except Exception as e:
        print("Startup user migration check failed:", e)


# ------------------------------------------------------------
# Utility Functions
# ------------------------------------------------------------

def calculate_zone(baseline: int, current_pefr: int):
    if baseline == 0:
        return ("Unknown", "Please set your baseline PEFR in your profile.", 0.0)

    percentage = (current_pefr / baseline) * 100

    if percentage >= 80:
        return ("Green", "You are in the Green Zone. Continue with your regular treatment plan.", percentage)
    elif 50 <= percentage < 80:
        return ("Yellow", "You are in the Yellow Zone. Use your reliever inhaler.", percentage)
    else:
        return ("Red", "Medical emergency. Seek immediate help.", percentage)


def get_pefr_trend(db: Session, owner_id: int, current_pefr: int):
    last_record = db.query(models.PEFRRecord).filter(
        models.PEFRRecord.owner_id == owner_id
    ).order_by(desc(models.PEFRRecord.recorded_at)).first()

    if not last_record:
        return "stable"
    if current_pefr > last_record.pefr_value:
        return "improving"
    elif current_pefr < last_record.pefr_value:
        return "worsening"
    return "stable"


def log_audit(db: Session, user_id: int, action: str, details: str = None):
    db_log = models.AuditLog(user_id=user_id, action=action, details=details)
    db.add(db_log)


def log_alert(db: Session, user_id: int, alert_type: str):
    db_alert = models.AlertLog(user_id=user_id, alert_type=alert_type)
    db.add(db_alert)

# ------------------------------------------------------------
# Root
# ------------------------------------------------------------

@app.get("/")
def read_root():
    return {"message": "Welcome to the PEFR Titration Tracker API"}


# Admin: view recent email send attempts (OTP/email logs)
@app.get("/admin/email-logs", response_model=List[schemas.EmailLog])
def get_email_logs(limit: int = 50, db: Session = Depends(database.get_db)):
    rows = db.query(models.EmailLog).order_by(desc(models.EmailLog.created_at)).limit(limit).all()
    return rows

# ------------------------------------------------------------
# AUTHENTICATION (OTP BASED ONLY)
# ------------------------------------------------------------

# 🔹 SIGNUP → SEND OTP
@app.post("/auth/signup-send-otp")
def signup_send_otp(user: schemas.UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):

    if auth.get_user(db, email=user.email):
        return JSONResponse(status_code=409, content={"error": "Email already exists"})

    otp = generate_otp()
    store_otp(
        email=user.email,
        otp=otp,
        purpose="signup",
        payload=user.dict()
    )

    # Decide whether to actually attempt SMTP sending or return OTP for dev/testing
    force_dev = os.getenv("OTP_FORCE_DEV_RETURN", "false").lower() in ("1", "true", "yes")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    # If dev mode forced or SMTP not configured, don't schedule background email and return OTP in response (dev only)
    if force_dev or not (smtp_user and smtp_pass):
        if not (smtp_user and smtp_pass):
            # warn in logs that SMTP isn't configured
            print("[auth] SMTP not configured; returning OTP in response for testing")
        else:
            print("[auth] OTP_FORCE_DEV_RETURN enabled; returning OTP in response")
        return {"message": "OTP generated (dev mode)", "otp": otp}

    # send email in background so response isn't delayed
    background_tasks.add_task(send_otp_email, user.email, otp, "Signup Verification")
    return {"message": "OTP sent to email"}


# 🔹 VERIFY OTP → CREATE USER
@app.post("/auth/verify-signup-otp")
def verify_signup_otp(
    email: str = Form(...),
    otp: str = Form(...),
    db: Session = Depends(database.get_db)
):

    success, data = verify_otp(email, otp, "signup")
    if not success:
        return JSONResponse(status_code=400, content={"error": data})

    user_data = data["payload"]
    hashed_password = auth.get_password_hash(user_data["password"])

    db_user = models.User(
        email=user_data["email"],
        name=user_data["name"],
        hashed_password=hashed_password,
        role=user_data["role"],
        age=user_data.get("age"),
        height=user_data.get("height"),
        gender=user_data.get("gender"),
        contact_number=user_data.get("contact_number"),
        address=user_data.get("address")
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    log_audit(db, db_user.id, "SIGNUP", f"OTP verified signup for {db_user.email}")
    db.commit()

    clear_otp(email)
    return {"message": "Signup successful. Please login."}


# 🔹 LOGIN (UNCHANGED)
@app.post("/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):

    user = auth.get_user(db, email=form_data.username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    if not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")

    access_token = auth.create_access_token(data={"sub": user.email})

    log_audit(db, user.id, "LOGIN", f"User {user.email} logged in")
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_role": user.role
    }


# 🔹 FORGOT PASSWORD → SEND OTP
@app.post("/auth/forgot-password")
def forgot_password(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(database.get_db)
):

    user = auth.get_user(db, email=email)
    if not user:
        return JSONResponse(status_code=404, content={"error": "Email not registered"})

    otp = generate_otp()
    store_otp(email, otp, "forgot")

    # If SMTP not configured or dev override, return OTP in response for testing
    force_dev = os.getenv("OTP_FORCE_DEV_RETURN", "false").lower() in ("1", "true", "yes")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    if force_dev or not (smtp_user and smtp_pass):
        if not (smtp_user and smtp_pass):
            print("[auth] SMTP not configured; returning OTP in response for testing")
        else:
            print("[auth] OTP_FORCE_DEV_RETURN enabled; returning OTP in response")
        return {"message": "OTP generated (dev mode)", "otp": otp}

    # schedule sending in background so API responds quickly
    background_tasks.add_task(send_otp_email, email, otp, "Password Reset")

    return {"message": "OTP sent to email"}


# 🔹 RESET PASSWORD → VERIFY OTP
@app.post("/auth/reset-password")
def reset_password(
    email: str = Form(...),
    otp: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(database.get_db)
):

    success, msg = verify_otp(email, otp, "forgot")
    if not success:
        return JSONResponse(status_code=400, content={"error": msg})

    user = auth.get_user(db, email=email)
    if not user:
        return JSONResponse(status_code=404, content={"error": "User not found"})

    user.hashed_password = auth.get_password_hash(new_password)
    db.commit()

    log_audit(db, user.id, "RESET_PASSWORD")
    db.commit()

    clear_otp(email)
    return {"message": "Password reset successful"}

# 🔹 VERIFY FORGOT PASSWORD OTP (checks OTP but does not clear it yet)
@app.post("/auth/verify-forgot-otp")
def verify_forgot_otp(
    email: str = Form(...),
    otp: str = Form(...),
    db: Session = Depends(database.get_db)
):

    success, msg = verify_otp(email, otp, "forgot")
    if not success:
        return JSONResponse(status_code=400, content={"error": msg})

    # Do NOT clear the OTP here; allow the client to proceed to reset-password which will
    # verify again or consume the OTP as part of reset. This endpoint is only for pre-verification UI flows.
    return {"message": "OTP valid"}
# ------------------------------------------------------------
# ⚠️ ALL OTHER ENDPOINTS BELOW ARE UNCHANGED
# (Profile, PEFR, Symptoms, Doctor, Medication, Reminder, etc.)
# ------------------------------------------------------------


# --- Profile Management Endpoints ---

@app.get("/profile/me", response_model=schemas.User)
def get_my_profile(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db) # Add the db session
):
    # 1. Manually load the Baseline (Fixes "N/A" issue)
    db_baseline = db.query(models.BaselinePEFR).filter(
        models.BaselinePEFR.owner_id == current_user.id
    ).first()
    current_user.baseline = db_baseline

    # 2. Manually load the latest PEFR record
    latest_pefr = db.query(models.PEFRRecord).filter(
        models.PEFRRecord.owner_id == current_user.id
    ).order_by(desc(models.PEFRRecord.recorded_at)).first()
    
    # 3. Manually load the latest Symptom record
    latest_symptom = db.query(models.Symptom).filter(
        models.Symptom.owner_id == current_user.id
    ).order_by(desc(models.Symptom.recorded_at)).first()
    
    # 4. Attach them to the user object
    current_user.latest_pefr_record = latest_pefr
    current_user.latest_symptom = latest_symptom
    
    return current_user

@app.put("/profile/me", response_model=schemas.User)
def update_my_profile(
    profile_update: schemas.UserCreate, 
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    current_user.name = profile_update.name
    current_user.age = profile_update.age
    current_user.height = profile_update.height
    current_user.gender = profile_update.gender
    current_user.contact_number = profile_update.contact_number
    current_user.address = profile_update.address
    
    if profile_update.password:
        current_user.hashed_password = auth.get_password_hash(profile_update.password)
        
    db.commit()
    db.refresh(current_user)
    log_audit(db, current_user.id, "UPDATE_PROFILE")
    db.commit()
    return current_user


@app.post("/profile/device-token")
def register_device_token(
    token: str = Form(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Register or update the current user's FCM device token."""
    # Create or update a Device record so a user can have multiple devices
    existing = db.query(models.Device).filter(models.Device.token == token).first()
    if existing:
        existing.owner_id = current_user.id
        existing.active = True
        try:
            existing.last_seen = datetime.datetime.utcnow()
        except Exception as e:
            print(f"[register_device_token] failed to set last_seen: {e}")
    else:
        dev = models.Device(owner_id=current_user.id, token=token, platform=None)
        db.add(dev)
    db.commit()
    return {"message": "Device token saved"}


@app.get("/profile/devices")
def list_my_devices(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    devices = db.query(models.Device).filter(models.Device.owner_id == current_user.id).all()
    return [
        {
            "id": d.id,
            "token": d.token,
            "platform": d.platform,
            "last_seen": d.last_seen,
            "active": d.active
        }
        for d in devices
    ]


@app.delete("/profile/devices/{device_id}")
def unregister_device(
    device_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    d = db.query(models.Device).filter(models.Device.id == device_id, models.Device.owner_id == current_user.id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    d.active = False
    db.commit()
    return {"message": "Device unregistered"}

@app.delete("/profile/me")
def delete_my_account(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Delete all related data first to maintain referential integrity
    
    # Delete PEFR records
    db.query(models.PEFRRecord).filter(models.PEFRRecord.owner_id == current_user.id).delete()
    
    # Delete symptom records
    db.query(models.Symptom).filter(models.Symptom.owner_id == current_user.id).delete()
    
    # Delete baseline
    db.query(models.BaselinePEFR).filter(models.BaselinePEFR.owner_id == current_user.id).delete()
    
    # Delete medications (both prescribed and owned)
    db.query(models.Medication).filter(models.Medication.owner_id == current_user.id).delete()
    db.query(models.Medication).filter(models.Medication.prescribed_by == current_user.id).delete()
    
    # Delete medication status history
    db.query(models.MedicationStatusHistory).filter(models.MedicationStatusHistory.changed_by_user_id == current_user.id).delete()
    
    # Delete notifications
    db.query(models.Notification).filter(models.Notification.owner_id == current_user.id).delete()
    
    # Delete emergency contacts
    db.query(models.EmergencyContact).filter(models.EmergencyContact.owner_id == current_user.id).delete()
    
    # Delete devices
    db.query(models.Device).filter(models.Device.owner_id == current_user.id).delete()
    
    # Delete push logs
    db.query(models.PushLog).filter(models.PushLog.owner_id == current_user.id).delete()
    
    # Delete doctor-patient links (both as doctor and patient)
    db.query(models.DoctorPatient).filter(
        (models.DoctorPatient.doctor_id == current_user.id) | 
        (models.DoctorPatient.patient_id == current_user.id)
    ).delete()
    
    # Delete audit logs
    db.query(models.AuditLog).filter(models.AuditLog.user_id == current_user.id).delete()
    
    # Delete alert logs
    db.query(models.AlertLog).filter(models.AlertLog.user_id == current_user.id).delete()
    
    # Finally delete the user
    db.delete(current_user)
    db.commit()
    
    return {"message": "Account deleted successfully"}

# --- Asthma Management Endpoints ---

@app.post("/patient/baseline", response_model=schemas.BaselinePEFR)
def set_baseline(
    baseline: schemas.BaselinePEFRCreate, 
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Only patients can set a baseline.")
    
    db_baseline = db.query(models.BaselinePEFR).filter(models.BaselinePEFR.owner_id == current_user.id).first()
    
    if db_baseline:
        db_baseline.baseline_value = baseline.baseline_value
        log_audit(db, current_user.id, "UPDATE_BASELINE", f"Value: {baseline.baseline_value}")
    else:
        db_baseline = models.BaselinePEFR(**baseline.dict(), owner_id=current_user.id)
        db.add(db_baseline)
        log_audit(db, current_user.id, "CREATE_BASELINE", f"Value: {baseline.baseline_value}")
    
    db.commit()
    db.refresh(db_baseline)
    return db_baseline

@app.post("/pefr/record", response_model=schemas.PEFRRecordResponse)
def record_pefr(
    pefr: schemas.PEFRRecordCreate,
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Only patients can record PEFR.")

    baseline = db.query(models.BaselinePEFR).filter(models.BaselinePEFR.owner_id == current_user.id).first()
    
    baseline_value = 0
    if baseline:
        baseline_value = baseline.baseline_value

    zone, guidance, percentage = calculate_zone(baseline_value, pefr.pefr_value)
    trend = get_pefr_trend(db, current_user.id, pefr.pefr_value)
    
    db_record = models.PEFRRecord(
        pefr_value=pefr.pefr_value,
        zone=zone,
        owner_id=current_user.id,
        percentage=percentage,
        trend=trend,
        source=pefr.source
    )
    db.add(db_record)
    
    # Update baseline PEFR if this PEFR value is higher than current baseline
    if baseline:
        if pefr.pefr_value > baseline.baseline_value:
            baseline.baseline_value = pefr.pefr_value
            log_audit(db, current_user.id, "UPDATE_BASELINE_AUTO", f"Updated to highest PEFR: {pefr.pefr_value}")
    else:
        # For new users, set baseline to the first PEFR value
        new_baseline = models.BaselinePEFR(baseline_value=pefr.pefr_value, owner_id=current_user.id)
        db.add(new_baseline)
        log_audit(db, current_user.id, "CREATE_BASELINE_AUTO", f"Set initial baseline to PEFR: {pefr.pefr_value}")
    
    if zone == "Red":
        log_alert(db, current_user.id, "RED_ZONE_TRIGGERED")
    
    log_audit(db, current_user.id, "RECORD_PEFR", f"Value: {pefr.pefr_value}, Zone: {zone}")
    
    db.commit()
    db.refresh(db_record)
    
    # Send notification to linked doctors
    try:
        # Find all doctors linked to this patient
        doctor_links = db.query(models.DoctorPatient).filter(models.DoctorPatient.patient_id == current_user.id).all()
        doctor_ids = [link.doctor_id for link in doctor_links]
        
        if doctor_ids:
            notif_msg = f"Patient {current_user.name} recorded PEFR: {pefr.pefr_value} L/min (Zone: {zone}, {percentage:.1f}%)"
            notif_link = f"/patient/{current_user.id}/pefr"
            
            # Create notifications for all linked doctors
            for doctor_id in doctor_ids:
                notification = models.Notification(owner_id=doctor_id, message=notif_msg, link=notif_link)
                db.add(notification)
            db.commit()
            
            # Send push notifications to all linked doctors
            for doctor_id in doctor_ids:
                try:
                    # Get all active device tokens for this doctor
                    devices = db.query(models.Device).filter(models.Device.owner_id == doctor_id, models.Device.active == True).all()
                    tokens = [d.token for d in devices]
                    if tokens:
                        res = firebase_messaging.send_messages_to_tokens(tokens, title="Patient PEFR Update", body=notif_msg, data={"link": notif_link, "patient_id": str(current_user.id)})
                        # Record push logs
                        for r in (res.get('responses') or []):
                            log = models.PushLog(owner_id=doctor_id, token=r.get('token'), success=bool(r.get('success')), response=str(r.get('response')) if r.get('response') else None, error=str(r.get('error')) if r.get('error') else None)
                            db.add(log)
                        db.commit()
                        # Deactivate tokens that failed with invalid registration
                        for r in (res.get('responses') or []):
                            if not r.get('success'):
                                tkn = r.get('token')
                                db.query(models.Device).filter(models.Device.token == tkn).update({"active": False})
                        db.commit()
                except Exception as e:
                    print(f"Failed to send FCM to doctor {doctor_id}: {e}")
                    db.rollback()
    except Exception as e:
        # Non-fatal: if notification fails, proceed to return PEFR record
        print(f"Failed to create/send PEFR notifications: {e}")
        db.rollback()
    
    return schemas.PEFRRecordResponse(
        zone=zone,
        guidance=guidance,
        record=db_record,
        percentage=percentage,
        trend=trend
    )

@app.post("/symptom/record", response_model=schemas.Symptom)
def record_symptom(
    symptom: schemas.SymptomCreate,
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Only patients can record symptoms.")
        
    db_symptom = models.Symptom(
        **symptom.dict(),
        owner_id=current_user.id
    )
    db.add(db_symptom)
    log_audit(db, current_user.id, "RECORD_SYMPTOM")
    db.commit()
    db.refresh(db_symptom)
    return db_symptom


# -----------------------------
# ML Prediction Endpoint
# -----------------------------
@app.post("/ml/predict", response_model=schemas.MLPrediction)
def ml_predict(
    payload: schemas.MLInput,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Only patients should use patient-specific recommendations
    if current_user.role != models.UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Only patients can request ML predictions.")

    try:
        predictor = get_predictor()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    features = payload.dict()
    result = predictor.predict(features)

    # Log the usage for audit
    log_audit(db, current_user.id, "ML_PREDICT", f"Input: {features}, Output: {result}")
    db.commit()

    return schemas.MLPrediction(**result)


# --- PATIENT-VIEW ENDPOINTS ---

@app.get("/pefr/records", response_model=List[schemas.PEFRRecord])
def get_my_pefr_records(
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Only patients can view this data.")
    
    records = db.query(models.PEFRRecord).filter(
        models.PEFRRecord.owner_id == current_user.id
    ).order_by(models.PEFRRecord.recorded_at.asc()).all()
    return records


@app.get("/symptom/records", response_model=List[schemas.Symptom])
def get_my_symptom_records(
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Only patients can view this data.")
    
    records = db.query(models.Symptom).filter(
        models.Symptom.owner_id == current_user.id
    ).order_by(models.Symptom.recorded_at.asc()).all()
    return records


# --- DOCTOR LINKING ---

@app.post("/patient/link-doctor", response_model=schemas.DoctorPatientLink)
def link_patient_to_doctor(
    link_request: schemas.DoctorPatientLinkCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Only patients can link to a doctor.")

    doctor = db.query(models.User).filter(
        models.User.email == link_request.doctor_email,
        models.User.role == models.UserRole.DOCTOR
    ).first()

    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found with that email.")

    existing_link = db.query(models.DoctorPatient).filter(
        models.DoctorPatient.doctor_id == doctor.id,
        models.DoctorPatient.patient_id == current_user.id
    ).first()

    if existing_link:
        return existing_link

    db_link = models.DoctorPatient(
        doctor_id=doctor.id,
        patient_id=current_user.id
    )
    db.add(db_link)
    db.commit()
    db.refresh(db_link)

    log_audit(db, current_user.id, "LINK_DOCTOR", f"Patient linked to doctor ID {doctor.id}")
    db.commit()

    return db_link


# --- MEDICATION ENDPOINTS ---

@app.post("/medications", response_model=schemas.Medication)
def create_medication(
    medication: schemas.MedicationCreate,
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    # allow API to set `source` if provided (e.g., 'ai' when saved from ML recommendation)
    payload = medication.dict()
    db_medication = models.Medication(**payload, owner_id=current_user.id)
    # Set initial doses_remaining if days provided (best-effort)
    if getattr(medication, 'days', None) is not None and getattr(db_medication, 'doses_remaining', None) is None:
        try:
            db_medication.doses_remaining = int(medication.days)
        except Exception:
            pass

    db.add(db_medication)
    db.commit()
    db.refresh(db_medication)
    return db_medication

@app.get("/medications", response_model=List[schemas.Medication])
def get_my_medications(
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.Medication).filter(models.Medication.owner_id == current_user.id).all()

# --- UPDATE MEDICATION STATUS (PATIENT) ---

@app.patch("/medications/{med_id}/status")
def update_medication_status(
    med_id: int,
    update: schemas.MedicationStatusUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    med = db.query(models.Medication).filter(
        models.Medication.id == med_id,
        models.Medication.owner_id == current_user.id
    ).first()

    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    # 1) update current status on medication
    med.taken_status = update.status

    # 2) create history record
    history = models.MedicationStatusHistory(
        medication_id = med.id,
        status = update.status,
        notes = update.notes,
        changed_by_user_id = current_user.id
    )
    db.add(history)

    log_audit(db, current_user.id, "UPDATE_MEDICATION_STATUS", f"Medication {med.id} -> {update.status}")
    db.commit()
    # Notify prescribing doctor (or linked doctor) about the status update
    try:
        doctor_id = med.prescribed_by
        if not doctor_id:
            link = db.query(models.DoctorPatient).filter(models.DoctorPatient.patient_id == med.owner_id).first()
            doctor_id = link.doctor_id if link else None

        if doctor_id and doctor_id != current_user.id:
            msg = f"Patient {current_user.name} updated status for {med.name} to {update.status}."
            notif = models.Notification(owner_id=doctor_id, message=msg, link=f"/medications/{med.id}")
            db.add(notif)
            db.commit()
            try:
                devices = db.query(models.Device).filter(models.Device.owner_id == doctor_id, models.Device.active == True).all()
                tokens = [d.token for d in devices]
                if tokens:
                    res = firebase_messaging.send_messages_to_tokens(tokens, title="Medication Status Updated", body=msg, data={"link": f"/medications/{med.id}"})
                    for r in (res.get('responses') or []):
                        log = models.PushLog(owner_id=doctor_id, token=r.get('token'), success=bool(r.get('success')), response=str(r.get('response')) if r.get('response') else None, error=str(r.get('error')) if r.get('error') else None)
                        db.add(log)
                    db.commit()
                    for r in (res.get('responses') or []):
                        if not r.get('success'):
                            db.query(models.Device).filter(models.Device.token == r.get('token')).update({"active": False})
                    db.commit()
            except Exception:
                db.rollback()
    except Exception:
        db.rollback()
    return {"message": "Status updated"}


@app.patch("/medications/{med_id}", response_model=schemas.Medication)
def update_medication_metadata(
    med_id: int,
    update: schemas.MedicationUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    med = db.query(models.Medication).filter(models.Medication.id == med_id).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    # Only owner or doctor may edit
    if med.owner_id != current_user.id and current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Not allowed to edit this medication")

    # apply updates if provided
    fields = ['name', 'dose', 'schedule', 'start_date', 'days', 'cure_probability', 'doses_remaining']
    for f in fields:
        if hasattr(update, f) and getattr(update, f) is not None:
            setattr(med, f, getattr(update, f))

    db.commit()
    db.refresh(med)
    log_audit(db, current_user.id, "UPDATE_MEDICATION_METADATA", f"Medication {med.id} metadata updated")
    return med


@app.post("/medications/{med_id}/take", response_model=schemas.Medication)
def take_medication(
    med_id: int,
    take: schemas.MedicationTake,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Only patients may mark doses as taken
    if current_user.role != models.UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Only patients can mark medication as taken")

    med = db.query(models.Medication).filter(models.Medication.id == med_id, models.Medication.owner_id == current_user.id).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    doses = max(1, int(getattr(take, 'doses', 1) or 1))
    if med.doses_remaining is not None:
        med.doses_remaining = max(0, med.doses_remaining - doses)

    med.taken_status = 'taken'

    history = models.MedicationStatusHistory(
        medication_id = med.id,
        status = 'taken',
        notes = take.notes,
        changed_by_user_id = current_user.id
    )
    db.add(history)

    log_audit(db, current_user.id, "MEDICATION_TAKEN", f"Medication {med.id} taken, doses={doses}")
    db.commit()
    db.refresh(med)

    # Notify prescribing doctor (or linked doctor) that patient took medication
    try:
        doctor_id = med.prescribed_by
        if not doctor_id:
            link = db.query(models.DoctorPatient).filter(models.DoctorPatient.patient_id == med.owner_id).first()
            doctor_id = link.doctor_id if link else None

        if doctor_id and doctor_id != current_user.id:
            msg = f"Patient {current_user.name} marked {med.name} as taken."
            notif = models.Notification(owner_id=doctor_id, message=msg, link=f"/medications/{med.id}")
            db.add(notif)
            db.commit()
            try:
                devices = db.query(models.Device).filter(models.Device.owner_id == doctor_id, models.Device.active == True).all()
                tokens = [d.token for d in devices]
                if tokens:
                    res = firebase_messaging.send_messages_to_tokens(tokens, title="Medication Taken", body=msg, data={"link": f"/medications/{med.id}"})
                    for r in (res.get('responses') or []):
                        log = models.PushLog(owner_id=doctor_id, token=r.get('token'), success=bool(r.get('success')), response=str(r.get('response')) if r.get('response') else None, error=str(r.get('error')) if r.get('error') else None)
                        db.add(log)
                    db.commit()
                    for r in (res.get('responses') or []):
                        if not r.get('success'):
                            db.query(models.Device).filter(models.Device.token == r.get('token')).update({"active": False})
                    db.commit()
            except Exception:
                db.rollback()
    except Exception:
        db.rollback()

    return med

# --- GET MEDICATION HISTORY (DOCTOR) ---

@app.get("/doctor/patient/{patient_id}/medications/history", response_model=List[schemas.MedicationWithHistory])
def get_patient_medication_history(
    patient_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Only doctors can access this endpoint")

    meds = db.query(models.Medication).filter(models.Medication.owner_id == patient_id).all()
    result = []

    for m in meds:
        histories = db.query(models.MedicationStatusHistory).filter(
            models.MedicationStatusHistory.medication_id == m.id
        ).order_by(desc(models.MedicationStatusHistory.changed_at)).all()

        mapped = schemas.MedicationWithHistory(
            id = m.id,
            owner_id = m.owner_id,
            name = m.name,
            dose = m.dose,
            schedule = m.schedule,
            taken_status = m.taken_status,
            start_date = m.start_date,
            days = m.days,
            cure_probability = m.cure_probability,
            doses_remaining = m.doses_remaining,
            status_history = histories
        )
        result.append(mapped)

    return result


# --- DELETE LINKED PATIENT (DOCTOR) ---
@app.delete("/doctor/patient/{patient_id}")
def delete_linked_patient(
    patient_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Only doctors can remove linked patients")

    link = db.query(models.DoctorPatient).filter(
        models.DoctorPatient.doctor_id == current_user.id,
        models.DoctorPatient.patient_id == patient_id
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    db.delete(link)
    log_audit(db, current_user.id, "DELETE_PATIENT_LINK", f"Unlinked patient {patient_id}")
    db.commit()
    return {"message": "Unlinked"}


# --- GET LINKED DOCTOR FOR CURRENT PATIENT ---
@app.get("/patient/doctor", response_model=schemas.User)
def get_linked_doctor(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # find doctor link where current_user is patient
    link = db.query(models.DoctorPatient).filter(models.DoctorPatient.patient_id == current_user.id).first()
    if not link:
        raise HTTPException(status_code=404, detail="No linked doctor")

    doctor = db.query(models.User).filter(models.User.id == link.doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    return doctor


# --- PATIENT: UNLINK DOCTOR ---
@app.delete("/patient/doctor")
def unlink_doctor(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # find the link where current_user is the patient
    link = db.query(models.DoctorPatient).filter(models.DoctorPatient.patient_id == current_user.id).first()
    if not link:
        raise HTTPException(status_code=404, detail="No linked doctor")

    db.delete(link)
    log_audit(db, current_user.id, "UNLINK_DOCTOR", f"Patient {current_user.id} unlinked doctor {link.doctor_id}")
    db.commit()
    return {"message": "Unlinked"}


# --- DELETE MEDICATION (PATIENT or DOCTOR) ---
@app.delete("/medications/{med_id}")
def delete_medication(
    med_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    med = db.query(models.Medication).filter(models.Medication.id == med_id).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    # Doctors may remove medications they prescribed
    if current_user.role == models.UserRole.DOCTOR:
        db.delete(med)
        log_audit(db, current_user.id, "DELETE_MEDICATION", f"Doctor deleted medication {med_id}")
        db.commit()
        return {"message": "Deleted"}

    # Patients can delete their own medication only after updating status
    if med.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this medication")

    if not med.taken_status or med.taken_status.lower() == "not updated":
        raise HTTPException(status_code=400, detail="Please update medication status before deleting")

    db.delete(med)
    log_audit(db, current_user.id, "DELETE_MEDICATION", f"Patient deleted medication {med_id}")
    db.commit()
    return {"message": "Deleted"}

# --- EMERGENCY CONTACT ENDPOINTS ---

@app.post("/contacts", response_model=schemas.EmergencyContact)
def create_emergency_contact(
    contact: schemas.EmergencyContactCreate,
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    db_contact = models.EmergencyContact(**contact.dict(), owner_id=current_user.id)
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact

@app.get("/contacts", response_model=List[schemas.EmergencyContact])
def get_my_emergency_contacts(
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.EmergencyContact).filter(models.EmergencyContact.owner_id == current_user.id).all()

# --- REMINDERS ENDPOINTS ---

@app.post("/reminders", response_model=schemas.Reminder)
def create_reminder(
    reminder: schemas.ReminderCreate,
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    db_reminder = models.Reminder(**reminder.dict(), owner_id=current_user.id)
    db.add(db_reminder)
    db.commit()
    db.refresh(db_reminder)
    return db_reminder

@app.get("/reminders", response_model=List[schemas.Reminder])
def get_my_reminders(
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.Reminder).filter(models.Reminder.owner_id == current_user.id).all()

# --- DOCTOR DASHBOARD ---

@app.get("/doctor/patients", response_model=List[schemas.User])
def get_doctor_patients(
    search: Optional[str] = Query(None, description="Search by patient name or email"),
    zone: Optional[str] = Query(None, description="Filter by current risk zone (Red, Yellow, Green)"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Only doctors can access this endpoint.")
    
    patient_links = select(models.DoctorPatient.patient_id).filter(
        models.DoctorPatient.doctor_id == current_user.id
    )
    query = db.query(models.User).filter(models.User.id.in_(patient_links))
    
    if search:
        query = query.filter(
            (models.User.name.ilike(f"%{search}%")) |
            (models.User.email.ilike(f"%{search}%"))
        )
    
    if zone:
        query = query.join(models.PEFRRecord).filter(models.PEFRRecord.zone == zone)

    patients = query.all()

    # Manually attach latest records for every patient
    for patient in patients:
        patient.latest_pefr_record = db.query(models.PEFRRecord).filter(
            models.PEFRRecord.owner_id == patient.id
        ).order_by(desc(models.PEFRRecord.recorded_at)).first()
        
        patient.latest_symptom = db.query(models.Symptom).filter(
            models.Symptom.owner_id == patient.id
        ).order_by(desc(models.Symptom.recorded_at)).first()

    return patients

# --- DOCTOR: Patient-specific endpoints (pefr / symptoms / prescribe) ---

def get_patient_by_id(db: Session, patient_id: int):
    return db.query(models.User).filter(models.User.id == patient_id, models.User.role == models.UserRole.PATIENT).first()

@app.get("/patient/{patient_id}/pefr", response_model=List[schemas.PEFRRecord])
def get_patient_pefr_records(
    patient_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Only doctors can access this data.")
    
    patient = get_patient_by_id(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
        
    return db.query(models.PEFRRecord).filter(models.PEFRRecord.owner_id == patient_id).all()


@app.get("/patient/{patient_id}/symptoms", response_model=List[schemas.Symptom])
def get_patient_symptom_records(
    patient_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Only doctors can access this data.")
    
    patient = get_patient_by_id(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
        
    return db.query(models.Symptom).filter(models.Symptom.owner_id == patient_id).all()

@app.post("/doctor/patient/{patient_id}/medication", response_model=schemas.Medication)
def prescribe_medication(
    patient_id: int,
    medication: schemas.MedicationCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Only doctors can prescribe medication.")

    patient = get_patient_by_id(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
        
    # Ensure we don't pass duplicate 'source' if the incoming payload included it
    med_data = medication.dict()
    # Remove potential conflicting keys that we set explicitly below
    med_data.pop('source', None)
    med_data.pop('prescribed_by', None)
    db_medication = models.Medication(
        **med_data,
        owner_id=patient_id,
        source='doctor',
        prescribed_by=current_user.id
    )
    db.add(db_medication)
    
    log_audit(db, current_user.id, "PRESCRIBE_MEDICATION", f"Doctor prescribed {medication.name} to patient {patient_id}")
    db.commit()
    
    db.refresh(db_medication)
    # Create a notification for the patient to inform them
    try:
        notif_msg = f"Doctor {current_user.name} prescribed {db_medication.name} for you."
        notif_link = f"/medications/{db_medication.id}"
        notification = models.Notification(owner_id=patient_id, message=notif_msg, link=notif_link)
        db.add(notification)
        db.commit()
        db.refresh(notification)
        # Attempt to send push notification via FCM to the patient
        try:
            # send to all active device tokens for the patient
            devices = db.query(models.Device).filter(models.Device.owner_id == patient_id, models.Device.active == True).all()
            tokens = [d.token for d in devices]
            if tokens:
                res = firebase_messaging.send_messages_to_tokens(tokens, title="New Prescription", body=notif_msg, data={"link": notif_link})
                # record push logs
                for r in (res.get('responses') or []):
                    log = models.PushLog(owner_id=patient_id, token=r.get('token'), success=bool(r.get('success')), response=str(r.get('response')) if r.get('response') else None, error=str(r.get('error')) if r.get('error') else None)
                    db.add(log)
                db.commit()
                # deactivate tokens that failed with invalid registration
                for r in (res.get('responses') or []):
                    if not r.get('success'):
                        tkn = r.get('token')
                        db.query(models.Device).filter(models.Device.token == tkn).update({"active": False})
                db.commit()
        except Exception:
            db.rollback()
    except Exception:
        # Non-fatal: if notification creation fails, proceed to return medication
        db.rollback()

    return db_medication


# Notifications
@app.get("/notifications", response_model=List[schemas.Notification])
def get_my_notifications(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    notes = db.query(models.Notification).filter(models.Notification.owner_id == current_user.id).order_by(desc(models.Notification.created_at)).all()
    return notes


@app.patch("/notifications/{notif_id}/read", response_model=schemas.Notification)
def mark_notification_read(
    notif_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    notif = db.query(models.Notification).filter(models.Notification.id == notif_id, models.Notification.owner_id == current_user.id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.read = True
    db.commit()
    db.refresh(notif)
    return notif


# --- TEST / ADMIN FCM ENDPOINTS ---
@app.post("/test/send-fcm-token")
def test_send_fcm_token(
    token: str = Form(...),
    title: str = Form("Test"),
    body: str = Form("This is a test push")
):
    """Unprotected test endpoint to send an FCM push to a raw device token.
    Use only for local verification."""
    success = firebase_messaging.send_message_to_token(token, title=title, body=body)
    return {"sent": success}


@app.post("/admin/send-fcm-user")
def admin_send_fcm_to_user(
    user_id: int = Form(...),
    title: str = Form("Notification"),
    body: str = Form(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Authenticated endpoint to send FCM to a user by id. Useful for verification.
    Requires authentication token in the request (same auth as other endpoints).
    """
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # Send to all active devices for the user
    devices = db.query(models.Device).filter(models.Device.owner_id == user_id, models.Device.active == True).all()
    tokens = [d.token for d in devices]
    if not tokens:
        raise HTTPException(status_code=400, detail="User has no active device tokens")
    res = firebase_messaging.send_messages_to_tokens(tokens, title=title, body=body, data={})
    # Log results
    for r in (res.get('responses') or []):
        log = models.PushLog(owner_id=user_id, token=r.get('token'), success=bool(r.get('success')), response=str(r.get('response')) if r.get('response') else None, error=str(r.get('error')) if r.get('error') else None)
        db.add(log)
    db.commit()
    # Deactivate invalid tokens
    for r in (res.get('responses') or []):
        if not r.get('success'):
            db.query(models.Device).filter(models.Device.token == r.get('token')).update({"active": False})
    db.commit()
    return {"sent": True, "result": res}
