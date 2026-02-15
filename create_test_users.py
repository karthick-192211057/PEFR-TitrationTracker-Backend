from app import database, models, auth

from sqlalchemy.orm import Session


def create_user_if_missing(db: Session, email: str, password: str, name: str, role: models.UserRole):
    exists = db.query(models.User).filter(models.User.email == email).first()
    if exists:
        print(f"User {email} already exists (id={exists.id})")
        return exists

    hashed = auth.get_password_hash(password)
    u = models.User(email=email, name=name, hashed_password=hashed, role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    print(f"Created user {email} with id {u.id}")
    return u


if __name__ == '__main__':
    db = database.SessionLocal()
    try:
        patient_email = 'karticksaravanan0703@gmail.com'
        patient_pass = 'Abc@1234'
        doctor_email = 'jandajanda0709@gmail.com'
        doctor_pass = 'Abc@1234'

        create_user_if_missing(db, patient_email, patient_pass, 'Kartick Saravanan', models.UserRole.PATIENT)
        create_user_if_missing(db, doctor_email, doctor_pass, 'Janda Janda', models.UserRole.DOCTOR)
    finally:
        db.close()
