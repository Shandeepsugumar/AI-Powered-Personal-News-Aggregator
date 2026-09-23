import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

import os
import pathlib

# Get the absolute path to the project root (two levels up from database.py)
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "feedtoread.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

from sqlalchemy import event as sa_event

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})

@sa_event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ContentItem(Base):
    __tablename__ = "content_items"

    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    title = Column(String, nullable=True)
    raw_content = Column(Text, nullable=False)
    content_hash = Column(String, index=True, nullable=False)
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    processing_status = Column(String, default="pending")

class SummaryItem(Base):
    __tablename__ = "summary_items"

    id = Column(Integer, primary_key=True, index=True)
    content_id = Column(Integer, ForeignKey("content_items.id"))
    headline = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    is_news = Column(Boolean, default=True)
    event = Column(String, nullable=True)
    stance = Column(String, nullable=True)
    key_facts = Column(JSON, nullable=True)

class StoryGroup(Base):
    __tablename__ = "story_groups"

    id = Column(Integer, primary_key=True, index=True)
    headline = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    stance = Column(String, nullable=True)
    importance = Column(String, nullable=True) # lead, major, minor
    embedding = Column(JSON, nullable=True) # List of floats
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    sources = relationship("StorySource", back_populates="group")

class StorySource(Base):
    __tablename__ = "story_sources"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("story_groups.id"))
    content_id = Column(Integer, ForeignKey("content_items.id"))
    source_name = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    source_type = Column(String, nullable=False)

    group = relationship("StoryGroup", back_populates="sources")




# Create tables
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
