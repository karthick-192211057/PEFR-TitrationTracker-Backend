# asthma-backend/database.py

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Use SQLite for simple development. The database will be a file named 'pefrtitrationtracker.db'
SQLALCHEMY_DATABASE_URL = "sqlite:///./pefrtitrationtracker.db"

# SQLALCHEMY_DATABASE_URL = "postgresql://user:password@postgresserver/db" # Example for PostgreSQL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False} # check_same_thread is needed only for SQLite
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()