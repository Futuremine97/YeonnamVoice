"""SQLAlchemy 데이터베이스 설정 (SQLite, 프로토타입용)."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

os.makedirs(settings.data_dir, exist_ok=True)
DB_URL = f"sqlite:///{settings.data_dir}/efu.db"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  모델 등록
    os.makedirs(settings.voice_dir, exist_ok=True)
    os.makedirs(settings.audio_out_dir, exist_ok=True)
    Base.metadata.create_all(bind=engine)
