"""
mongo_sources.py — FastAPI router for /api/sources
Ports the Node.js sources.js routes 1:1:
  GET    /api/sources/active-targets  (public — used by extraction pipeline)
  GET    /api/sources                 (auth required)
  POST   /api/sources                 (auth required)
  PATCH  /api/sources/:id/toggle      (auth required)
  DELETE /api/sources/:id             (auth required)
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from beanie import PydanticObjectId

from db.mongo_models import Source
from api.mongo_auth import get_current_user, User

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _normalize_type(raw_type: str) -> str:
    """Match Node.js normalisation logic exactly."""
    t = raw_type.upper()
    if "YOUTUBE" in t:
        return "YOUTUBE"
    if "BLOG" in t:
        return "BLOG"
    if "NEWSLETTER" in t:
        return "NEWSLETTER"
    if "RSS" in t:
        return "RSS"
    return t


# ── Request body ─────────────────────────────────────────────────────────────

class SourceBody(BaseModel):
    # Accept both naming conventions the Node.js route accepted
    sourceName: Optional[str] = None
    sourceType: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/active-targets")
async def active_targets(type: Optional[str] = Query(default=None)):
    """
    Public endpoint — returns aggregated active source targets.
    Used by the YouTube extraction pipeline to know which channels to scrape.
    Mirrors the MongoDB aggregate in sources.js.
    """
    filter_query: dict = {"isActive": True}
    if type:
        filter_query["sourceType"] = type.upper()

    pipeline = [
        {"$match": filter_query},
        {
            "$group": {
                "_id": {"name": "$sourceName", "type": "$sourceType"},
                "subscribersCount": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 0,
                "sourceName": "$_id.name",
                "sourceType": "$_id.type",
                "subscribersCount": 1,
            }
        },
    ]

    collection = Source.get_pymongo_collection()
    cursor = collection.aggregate(pipeline)
    results = await cursor.to_list(length=None)
    return {"targets": results}


@router.get("")
async def list_sources(current_user: User = Depends(get_current_user)):
    """Return all sources for the authenticated user, newest first."""
    sources = await Source.find(
        Source.userId == current_user.id
    ).sort(-Source.addedAt).to_list()
    return {"sources": [s.to_frontend_dict() for s in sources]}


import subprocess
import sys
import os
from pathlib import Path
from fastapi import BackgroundTasks

from api.utils_extractor import trigger_extractors

@router.post("", status_code=201)
async def add_source(body: SourceBody, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):

    """Add or upsert a source for the authenticated user."""
    raw_name = body.sourceName or body.name
    raw_type = body.sourceType or body.type

    if not raw_name or not raw_type:
        raise HTTPException(status_code=400, detail="sourceName and sourceType are required")

    clean_name = raw_name.strip()
    clean_type = _normalize_type(raw_type)

    # Upsert on (userId, sourceName) — mirror findOneAndUpdate with upsert:true
    existing = await Source.find_one(
        Source.userId == current_user.id,
        Source.sourceName == clean_name,
    )
    if existing:
        existing.sourceType = clean_type
        existing.isActive = True
        await existing.save()
        if clean_type == "YOUTUBE":
            background_tasks.add_task(trigger_extractors)
        return {"source": existing.to_frontend_dict()}
    else:
        source = Source(
            userId=current_user.id,
            sourceName=clean_name,
            sourceType=clean_type,
            isActive=True,
        )
        await source.insert()
        if clean_type == "YOUTUBE":
            background_tasks.add_task(trigger_extractors)
        return {"source": source.to_frontend_dict()}


@router.patch("/{source_id}/toggle")
async def toggle_source(source_id: str, current_user: User = Depends(get_current_user)):
    """Toggle isActive for a source owned by the authenticated user."""
    try:
        oid = PydanticObjectId(source_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Source not found")

    source = await Source.find_one(Source.id == oid, Source.userId == current_user.id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    source.isActive = not source.isActive
    await source.save()
    return {"source": source.to_frontend_dict()}


@router.delete("/{source_id}")
async def delete_source(source_id: str, current_user: User = Depends(get_current_user)):
    """Remove a source owned by the authenticated user."""
    try:
        oid = PydanticObjectId(source_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Source not found")

    source = await Source.find_one(Source.id == oid, Source.userId == current_user.id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await source.delete()
    return {"message": "Source deleted successfully"}
