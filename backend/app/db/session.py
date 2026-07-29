from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


database_url = getattr(
    settings,
    "database_url",
    None,
)

if database_url is None:
    database_url = getattr(
        settings,
        "DATABASE_URL",
        None,
    )

if not database_url:
    raise RuntimeError(
        "DATABASE_URL is not configured."
    )


engine = create_engine(
    str(database_url),
    pool_size=15,
    max_overflow=5,
    pool_timeout=10,
    pool_recycle=1800,
    pool_pre_ping=True,
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)


def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
