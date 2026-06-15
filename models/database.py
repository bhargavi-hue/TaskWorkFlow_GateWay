import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# We default to postgresql with psycopg2-binary
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:Bhargavi@localhost:5432/taskworkflow")

try:
    # Attempt connecting to PostgreSQL
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # Check connection
    with engine.connect() as conn:
        pass
    print("SQLAlchemy: Successfully connected to PostgreSQL database.")
except Exception as e:
    # If connection fails or driver is missing, fallback to local SQLite database for ease of testing
    sqlite_path = "sqlite:///./taskworkflow.db"
    print(f"SQLAlchemy: Connection to PostgreSQL failed: {e}. Falling back to SQLite: {sqlite_path}")
    engine = create_engine(sqlite_path, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
