"""
mongo_models.py — Beanie document models mirroring the Mongoose schemas exactly.
Field names match the MongoDB collections created by the Node.js backend.
"""
from datetime import datetime
from typing import Optional, List
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Sub-documents (embedded, not top-level collections)
# ──────────────────────────────────────────────

class StorySource(BaseModel):
    name: str
    url: str
    type: Optional[str] = None  # YOUTUBE | BLOG | NEWSLETTER


class Story(BaseModel):
    id: str
    headline: str
    category: str
    image_url: Optional[str] = None
    stance: str = "Neutral"
    importance: str = "minor"  # lead | major | minor
    summary: str
    is_new: bool = True
    sources: List[StorySource] = []
    imageUrl: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ──────────────────────────────────────────────
# Top-level Beanie Documents (= MongoDB collections)
# ──────────────────────────────────────────────

class User(Document):
    name: str
    email: str
    password_hash: str
    last_checked_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"


class Source(Document):
    userId: PydanticObjectId
    sourceName: str
    sourceType: str = "YOUTUBE"  # YOUTUBE | NEWSLETTER | BLOG | RSS
    isActive: bool = True
    addedAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "sources"

    def to_frontend_dict(self) -> dict:
        """Serialize with the virtual fields the Node.js toJSON transform added."""
        d = {
            "_id": str(self.id),
            "id": str(self.id),
            "userId": str(self.userId),
            "sourceName": self.sourceName,
            "sourceType": self.sourceType,
            "name": self.sourceName,   # virtual alias
            "type": self.sourceType,   # virtual alias
            "isActive": self.isActive,
            "addedAt": self.addedAt.isoformat() + "Z" if self.addedAt else None,
        }
        return d


class Edition(Document):
    userId: PydanticObjectId
    editionNumber: int
    dateString: str          # "YYYY-MM-DD"
    stories: List[Story] = []
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "editions"


class UserStoryStatusMongo(Document):
    user_id: str
    story_id: str
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    read_at: Optional[datetime] = None

    class Settings:
        name = "user_story_status"

class ContentItemMongo(Document):
    source_name: str
    source_type: str
    source_url: str
    title: Optional[str] = None
    raw_content: str
    image_url: Optional[str] = None
    content_hash: str
    published_at: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    processing_status: str = "pending"

    class Settings:
        name = "content_items"

class SummaryItemMongo(Document):
    content_id: PydanticObjectId
    headline: str
    summary: str
    category: str
    image_url: Optional[str] = None
    is_news: bool = True
    event: Optional[str] = None
    stance: Optional[str] = None
    key_facts: Optional[dict] = None

    class Settings:
        name = "summary_items"

class StoryGroupMongo(Document):
    headline: str
    summary: str
    category: str
    image_url: Optional[str] = None
    stance: Optional[str] = None
    importance: Optional[str] = None
    embedding: Optional[List[float]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "story_groups"

class StorySourceMongo(Document):
    story_id: PydanticObjectId
    content_id: Optional[PydanticObjectId] = None
    source_name: str
    source_url: str
    source_type: str
    is_new_contribution: bool = False
    emailed: bool = False

    class Settings:
        name = "story_sources"
