"""Движок и сессия БД. SQLite в v1 (Postgres — на пилоте, смена строки подключения)."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_DB = REPO_ROOT / "data" / "real" / "copilot.db"
_DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)

DB_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_DEFAULT_DB}")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False}
                       if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
