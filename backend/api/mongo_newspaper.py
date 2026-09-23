"""
mongo_newspaper.py — FastAPI router for /api/newspaper
Ports the Node.js newspaper.js routes 1:1:
  GET  /api/newspaper/latest          (auth required)
  POST /api/newspaper/refresh         (auth required)
  GET  /api/newspaper/archive         (auth required, ?date=YYYY-MM-DD)
  GET  /api/newspaper/archives        (auth required)
  GET  /api/newspaper/edition/:id     (auth required)

Stories come from newsletter_stage.json if present, otherwise from BASE_STORIES fallback.
"""
import os
import json
import time
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from beanie import PydanticObjectId

from db.mongo_models import Edition, Story, StorySource, User
from api.mongo_auth import get_current_user
from datetime import datetime, timezone
from typing import List, Optional
from db.database import SessionLocal, StoryGroup

router = APIRouter(prefix="/api/newspaper", tags=["newspaper"])

# ── Path to newsletter_stage.json (same relative path as in Node backend) ────
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
STAGE_JSON_PATH = os.path.join(_BACKEND_DIR, "newsletter_service", "newsletter_stage.json")

# ── Fallback stories (identical to Node BASE_STORIES) ────────────────────────
BASE_STORIES = [
    {"id": "story-001", "headline": "Apple Unveils M4 Silicon with Dedicated Local AI Acceleration", "category": "Technology", "stance": "Neutral", "importance": "lead", "summary": "Apple officially debuted its next-generation M4 architecture, placing unprecedented emphasis on local inference capabilities and power efficiency. The silicon redesign targets demanding on-device neural workloads without forcing users to offload computations to cloud services.", "sources": [{"name": "MKBHD", "url": "https://youtube.com", "type": "YOUTUBE"}, {"name": "TechCrunch", "url": "https://techcrunch.com", "type": "BLOG"}]},
    {"id": "story-002", "headline": "OpenAI Releases Open Weights Research Suite to Global Labs", "category": "Technology", "stance": "Positive", "importance": "major", "summary": "In an unexpected strategic shift, the research team published weights for an open alignment model, emphasizing collaborative safety audits and decentralized model verification.", "sources": [{"name": "The Verge", "url": "https://theverge.com", "type": "BLOG"}]},
    {"id": "story-003", "headline": "Critique: The Fragile Economics of Subsidized Cloud Compute", "category": "Opinion", "stance": "Negative", "importance": "major", "summary": "Escalating operational expenses for generative workloads are threatening software startup margins. Industry observers warn that current flat-rate pricing models cannot survive high-token production usage.", "sources": [{"name": "Stratechery", "url": "https://stratechery.com", "type": "NEWSLETTER"}]},
    {"id": "story-004", "headline": "SpaceX Completes 48-Hour Rapid Turnaround Booster Milestone", "category": "Science", "stance": "Neutral", "importance": "minor", "summary": "Operational cadence reached a new peak this morning as commercial launch crews cleared static fire tests and turnaround inspections in under two days.", "sources": [{"name": "Everyday Astronaut", "url": "https://youtube.com", "type": "YOUTUBE"}]},
    {"id": "story-005", "headline": "Frontier AI Governance Framework Ratified by 18 Global Nations", "category": "Technology", "stance": "Positive", "importance": "major", "summary": "An international accord setting rigorous testing benchmarks for multi-modal sovereign models was signed today, establishing standardized audit criteria for high-compute datacenters.", "sources": [{"name": "Financial Times", "url": "https://ft.com", "type": "BLOG"}, {"name": "Stratechery", "url": "https://stratechery.com", "type": "NEWSLETTER"}]},
    {"id": "story-006", "headline": "Solid-State Battery Breakthrough Yields 800-Mile Density Lab Test", "category": "Science", "stance": "Positive", "importance": "minor", "summary": "Researchers demonstrate a dendrite-resistant ceramic separator that operates stably through 1,200 fast-charge thermal cycles without measurable degradation.", "sources": [{"name": "Ars Technica", "url": "https://arstechnica.com", "type": "BLOG"}]},
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _local_date_string(d: Optional[datetime] = None) -> str:
    """Return YYYY-MM-DD in local time (mirrors getLocalDateString in Node)."""
    d = d or datetime.now()
    return d.strftime("%Y-%m-%d")


def _get_live_stories(edition_number: int = 1, now: Optional[datetime] = None) -> List[Story]:
    """
    Load stories from SQLite StoryGroup table (the final AI summary).
    Falls back to BASE_STORIES if database is empty.
    """
    now = now or datetime.utcnow()
    
    try:
        db = SessionLocal()
        groups = db.query(StoryGroup).all()
        
        if groups:
            NEWS_CATEGORIES = ["TECHNOLOGY", "BUSINESS", "SPORTS", "POLITICS", "SCIENCE"]
            
            def sort_key(g):
                cat = (g.category or "").upper()
                tier = 0 if cat in NEWS_CATEGORIES else 1
                importance_score = 0
                if g.importance == "lead": importance_score = 0
                elif g.importance == "major": importance_score = 1
                elif g.importance == "minor": importance_score = 2
                elif g.importance == "feature": importance_score = 3
                else: importance_score = 4
                
                ts = g.created_at.timestamp() if g.created_at else 0
                return (tier, importance_score, -ts)
            
            groups.sort(key=sort_key)

            stories = []
            for idx, group in enumerate(groups):
                cat = (group.category or "Technology").upper()
                is_news = cat in NEWS_CATEGORIES
                if not is_news:
                    importance = "feature"
                else:
                    importance = group.importance if group.importance in ["lead", "major", "minor"] else "minor"
                
                sources = []
                for s in group.sources:
                    sources.append(StorySource(name=s.source_name, url=s.source_url, type=s.source_type.upper()))
                
                if not sources:
                    sources.append(StorySource(name="Digital Wire", url="https://news.google.com", type="BLOG"))
                
                stance_val = group.stance.upper() if group.stance else "NEUTRAL"
                stance_str = f"{stance_val} STANCE" if "STANCE" not in stance_val else stance_val
                
                story_id = str(group.id)
                stories.append(Story(
                    id=story_id,
                    headline=group.headline,
                    category=cat,
                    stance=stance_str,
                    importance=importance,
                    summary=group.summary,
                    imageUrl=None,
                    sources=sources,
                    timestamp=group.created_at or now,
                    is_new=True
                ))
            db.close()
            return stories
    except Exception as e:
        print(f"[newspaper] Error reading from SQLite database: {e}")

    # Fallback to BASE_STORIES
    # Fallback to BASE_STORIES
    return [
        Story(
            id=f"story-ed{edition_number}-{idx + 1}-{int(time.time()):x}",
            headline=s["headline"],
            category=s["category"],
            stance=s["stance"],
            importance=s["importance"],
            summary=s["summary"],
            sources=[StorySource(**src) for src in s["sources"]],
            timestamp=datetime.fromtimestamp(now.timestamp() - idx * 12 * 60),
        )
        for idx, s in enumerate(BASE_STORIES)
    ]


def _edition_to_dict(edition: Edition) -> dict:
    """Serialise an Edition document to a JSON-safe dict."""
    return {
        "_id": str(edition.id),
        "userId": str(edition.userId),
        "editionNumber": edition.editionNumber,
        "dateString": edition.dateString,
        "createdAt": edition.createdAt.isoformat() + "Z" if edition.createdAt else None,
        "stories": [
            {
                "id": s.id,
                "headline": s.headline,
                "category": s.category,
                "stance": s.stance,
                "importance": s.importance,
                "summary": s.summary,
                "imageUrl": s.imageUrl,
                "is_new": getattr(s, "is_new", True),
                "timestamp": s.timestamp.isoformat() + "Z" if s.timestamp else None,
                "sources": [{"name": src.name, "url": src.url, "type": src.type} for src in s.sources],
            }
            for s in edition.stories
        ],
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/latest")
async def get_latest(current_user: User = Depends(get_current_user)):
    """
    Return the latest edition for today.
    If none exists, auto-create Edition #1 (mirrors Node behaviour exactly).
    """
    today = _local_date_string()
    todays_editions = await Edition.find(
        Edition.userId == current_user.id,
        Edition.dateString == today,
    ).sort(-Edition.editionNumber).to_list()

    if not todays_editions:
        now = datetime.utcnow()
        stories = _get_live_stories(1, now)
        first_edition = Edition(
            userId=current_user.id,
            editionNumber=1,
            dateString=today,
            stories=stories,
            createdAt=now,
        )
        await first_edition.insert()
        # Update user.last_checked_at
        current_user.last_checked_at = now
        await current_user.save()
        return _edition_to_dict(first_edition)

    return _edition_to_dict(todays_editions[0])


@router.post("/refresh")
async def refresh(current_user: User = Depends(get_current_user)):
    """
    Generate a new edition with deduplicated stories.
    Returns {isNew, edition, message} - mirrors Node behaviour exactly.
    """
    today = _local_date_string()
    now = datetime.utcnow()

    prior_editions = await Edition.find(
        Edition.userId == current_user.id,
        Edition.dateString == today,
    ).sort(+Edition.editionNumber).to_list()

    seen_urls: set = set()
    seen_headlines: set = set()
    seen_ids: set = set()
    for ed in prior_editions:
        for story in ed.stories:
            seen_ids.add(str(story.id))
            if story.sources and story.sources[0].url:
                seen_urls.add(story.sources[0].url.strip().lower())
            if story.headline:
                seen_headlines.add(story.headline.strip().lower())

    candidates = _get_live_stories()
    
    next_num = len(prior_editions) + 1
    
    for art in candidates:
        url_match = (art.sources[0].url.strip().lower() if art.sources else "") in seen_urls
        headline_match = art.headline.strip().lower() in seen_headlines
        id_match = str(art.id) in seen_ids
        if id_match or url_match or headline_match:
            art.is_new = False
        else:
            art.is_new = True

    new_edition = Edition(
        userId=current_user.id,
        editionNumber=next_num,
        dateString=today,
        stories=candidates,
        createdAt=now,
    )
    await new_edition.insert()

    return {
        "isNew": True,
        "edition": _edition_to_dict(new_edition),
        "message": f"Edition #{next_num} hot off the presses.",
    }


@router.get("/archive")
async def get_archive(
    date: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    """
    Return all editions for a specific date.
    Accepts YYYY-MM-DD or DD/MM/YYYY (auto-converts).
    """
    if not date:
        raise HTTPException(status_code=400, detail="Date query param required (YYYY-MM-DD)")

    # Convert DD/MM/YYYY → YYYY-MM-DD
    if "/" in date:
        parts = date.split("/")
        if len(parts[0]) == 2:
            date = f"{parts[2]}-{parts[1]}-{parts[0]}"

    editions = await Edition.find(
        Edition.userId == current_user.id,
        Edition.dateString == date,
    ).sort(+Edition.editionNumber).to_list()

    return {"editions": [_edition_to_dict(e) for e in editions]}


@router.get("/archives")
async def get_archives(current_user: User = Depends(get_current_user)):
    """Return archive metadata grouped by date."""
    all_editions = await Edition.find(
        Edition.userId == current_user.id,
    ).sort(-Edition.createdAt).to_list()

    grouped: dict = {}
    for ed in all_editions:
        d = ed.dateString or _local_date_string(ed.createdAt)
        if d not in grouped:
            grouped[d] = []
        grouped[d].append({
            "_id": str(ed.id),
            "editionNumber": ed.editionNumber,
            "createdAt": ed.createdAt.isoformat() + "Z" if ed.createdAt else None,
        })

    result = [
        {
            "date": date,
            "count": len(eds),
            "editions": sorted(eds, key=lambda e: e["editionNumber"]),
        }
        for date, eds in grouped.items()
    ]
    return result


@router.get("/edition/{edition_id}")
async def get_edition(edition_id: str, current_user: User = Depends(get_current_user)):
    """Fetch a specific historical edition by _id."""
    try:
        oid = PydanticObjectId(edition_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Edition not found or unauthorized")

    edition = await Edition.find_one(
        Edition.id == oid,
        Edition.userId == current_user.id,
    )
    if not edition:
        raise HTTPException(status_code=404, detail="Edition not found or unauthorized")

    return _edition_to_dict(edition)


from pydantic import BaseModel
class MarkReadRequest(BaseModel):
    user_id: str
    story_id: str

@router.post("/mark_read")
async def mark_read(req: MarkReadRequest, current_user: User = Depends(get_current_user)):
    from db.mongo_models import UserStoryStatusMongo
    status = await UserStoryStatusMongo.find_one(
        UserStoryStatusMongo.user_id == req.user_id,
        UserStoryStatusMongo.story_id == req.story_id
    )
    if not status:
        status = UserStoryStatusMongo(user_id=req.user_id, story_id=req.story_id)
        await status.insert()
    
    status.read_at = datetime.utcnow()
    await status.save()
    return {"status": "success", "message": "Story marked as read"}
