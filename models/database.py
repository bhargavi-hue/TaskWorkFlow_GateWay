import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ❗ DO NOT use fallback in production
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("❌ DATABASE_URL is not set. Configure it in Render environment variables.")

# ✅ Create engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# ✅ Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ✅ Base
Base = declarative_base()

# ✅ Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()