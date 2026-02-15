# otp_service.py

import os
from dotenv import load_dotenv
import random
import logging
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
try:
    import requests
except Exception:
    requests = None

logger = logging.getLogger("otp_service")

OTP_EXPIRY_MINUTES = 2

# email -> { otp, created_at, purpose, payload }
otp_store = {}

# Load .env in project root (if present) so SMTP credentials can be provided via a file
_here = os.path.dirname(__file__)
_project_root = os.path.dirname(_here)  # Go up from app/ to project root
load_dotenv(os.path.join(_project_root, '.env'))
# Also try loading from app directory as fallback
load_dotenv(os.path.join(_here, '.env'))


def generate_otp():
    return str(random.randint(100000, 999999))


def store_otp(email: str, otp: str, purpose: str, payload: dict = None):
    otp_store[email] = {
        "otp": otp,
        "created_at": datetime.utcnow(),
        "purpose": purpose,
        "payload": payload
    }


def is_expired(email: str):
    return datetime.utcnow() - otp_store[email]["created_at"] > timedelta(minutes=OTP_EXPIRY_MINUTES)


def verify_otp(email: str, otp: str, purpose: str):
    if email not in otp_store:
        return False, "OTP not found"

    data = otp_store[email]

    if data["purpose"] != purpose:
        return False, "Invalid OTP purpose"

    if is_expired(email):
        del otp_store[email]
        return False, "OTP expired"

    if data["otp"] != otp:
        return False, "Invalid OTP"

    return True, data


def clear_otp(email: str):
    if email in otp_store:
        del otp_store[email]


def send_otp_email(email: str, otp: str, purpose: str):
    msg = MIMEText(
        f"Your OTP is: {otp}\n\n"
        f"Purpose: {purpose}\n"
        f"OTP is valid for {OTP_EXPIRY_MINUTES} minutes."
    )
    msg["Subject"] = os.getenv("OTP_EMAIL_SUBJECT", "PEFR Titration Tracker - OTP Verification")
    from_addr = os.getenv("OTP_EMAIL_FROM")
    msg["From"] = from_addr or "no-reply@pefrtitrationtracker.local"
    msg["To"] = email

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    # Developer override: force returning/printing OTP instead of sending email
    force_dev = os.getenv("OTP_FORCE_DEV_RETURN", "false").lower() in ("1", "true", "yes")

    # If SendGrid API key is configured, prefer using SendGrid REST API for reliability
    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    if sendgrid_key and requests is not None:
        try:
            sg_url = "https://api.sendgrid.com/v3/mail/send"
            payload = {
                "personalizations": [{"to": [{"email": email}], "subject": msg["Subject"]}],
                "from": {"email": from_addr or smtp_user or "no-reply@pefrtitrationtracker.local"},
                "content": [{"type": "text/plain", "value": msg.as_string()}]
            }
            headers = {"Authorization": f"Bearer {sendgrid_key}", "Content-Type": "application/json"}
            r = requests.post(sg_url, json=payload, headers=headers, timeout=int(os.getenv("SMTP_TIMEOUT", "15")))
            if r.status_code in (200, 202):
                logger.info(f"OTP email sent via SendGrid to {email}")
                return True
            else:
                logger.warning(f"SendGrid send failed ({r.status_code}): {r.text}")
        except Exception as e:
            logger.warning(f"SendGrid attempt failed: {e}")
    elif sendgrid_key and requests is None:
        logger.warning("SENDGRID_API_KEY is set but 'requests' package is not installed; skipping SendGrid attempt")

    # If SMTP credentials not configured, fallback to logging the OTP (dev mode)
    if not smtp_user or not smtp_pass or force_dev:
        if force_dev:
            logger.info("OTP_FORCE_DEV_RETURN enabled — printing OTP and skipping SMTP send")
        else:
            logger.warning("SMTP credentials not configured — falling back to console output for OTP delivery")
        print(f"[otp_service] OTP for {email}: {otp} (purpose={purpose})")
        return False

    # Try to send via SMTP. We'll attempt SMTP over SSL (port 465) first for providers
    # that require implicit TLS (e.g. some Gmail setups), then fall back to STARTTLS
    # on the configured port (commonly 587). Increase timeout for flaky networks.
    attempts = 2
    last_exc = None
    # Prepare DB session writer if available
    db_writer = None
    try:
        from database import SessionLocal
        import models
        db_writer = SessionLocal
    except Exception:
        db_writer = None

    timeout = int(os.getenv("SMTP_TIMEOUT", "30"))
    methods = []
    # Try implicit SSL first (common on port 465)
    methods.append(("ssl", smtp_host, 465))
    # Then try explicit STARTTLS on the configured port
    methods.append(("starttls", smtp_host, smtp_port))

    for method_name, host, port in methods:
        for attempt in range(1, attempts + 1):
            try:
                if method_name == "ssl":
                    logger.debug(f"Trying SMTP_SSL to {host}:{port} (attempt {attempt})")
                    server = smtplib.SMTP_SSL(host, port, timeout=timeout)
                    server.ehlo()
                else:
                    logger.debug(f"Trying SMTP (STARTTLS if available) to {host}:{port} (attempt {attempt})")
                    server = smtplib.SMTP(host, port, timeout=timeout)
                    server.ehlo()
                    # prefer STARTTLS when available
                    try:
                        server.starttls()
                        server.ehlo()
                    except Exception:
                        # STARTTLS might not be supported; continue without it
                        logger.debug("STARTTLS not available or failed, continuing without it")

                server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr or smtp_user, [email], msg.as_string())
                try:
                    server.quit()
                except Exception:
                    try:
                        server.close()
                    except Exception:
                        pass

                logger.info(f"OTP email sent to {email} via {method_name}@{host}:{port}")
                # record success in DB if possible
                if db_writer:
                    try:
                        db = db_writer()
                        db.add(models.EmailLog(recipient=email, subject=msg["Subject"], purpose=purpose, success=True, error=None))
                        db.commit()
                        db.close()
                    except Exception:
                        pass
                return True
            except Exception as e:
                last_exc = e
                logger.warning(f"{method_name} attempt {attempt} failed to send OTP email to {email}: {e}")
                # record failure attempt
                if db_writer:
                    try:
                        db = db_writer()
                        db.add(models.EmailLog(recipient=email, subject=msg["Subject"], purpose=purpose, success=False, error=str(e)))
                        db.commit()
                        db.close()
                    except Exception:
                        pass

    # All attempts failed — log full exception and print OTP for developer debugging
    logger.exception(f"Failed to send OTP email to {email} after {attempts} attempts: {last_exc}")
    # Helpful hint: many campus or corporate networks block outbound SMTP (ports 25/465/587).
    # If you see connection timeouts or connection refused errors here, prefer using
    # an API-based provider (SendGrid) by setting SENDGRID_API_KEY in your environment,
    # which uses HTTPS and usually works on restricted networks.
    if last_exc is not None:
        msg = str(last_exc).lower()
        if "timed out" in msg or "connectionrefusederror" in msg or "connection refused" in msg:
            logger.error("SMTP connection failures detected. Network may be blocking SMTP ports.\n"
                         "Consider setting SENDGRID_API_KEY or using a provider that accepts HTTPS API calls.")
    # final fail record
    if db_writer:
        try:
            db = db_writer()
            db.add(models.EmailLog(recipient=email, subject=msg["Subject"], purpose=purpose, success=False, error=str(last_exc)))
            db.commit()
            db.close()
        except Exception:
            pass
    print(f"[otp_service] OTP for {email}: {otp} (purpose={purpose})")
    return False
