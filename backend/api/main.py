from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import json
import sys

from db.database import get_db, ContentItem, SummaryItem, StoryGroup, StorySource
from utils.content_parser import parse_content, compute_content_hash, is_meaningful_content
from ai_agent.ai_service import summarize_content, generate_embedding, merge_decision, check_models_available
from utils.ranking import recompute_importance_ranking
from db.mongo_db import init_mongo, close_mongo
from db.mongo_models import User, Source, Edition, UserStoryStatusMongo
from api.mongo_auth import router as auth_router
from api.mongo_sources import router as sources_router
from api.mongo_newspaper import router as mongo_newspaper_router
import io
import threading
from contextlib import contextmanager

# Thread-local storage for standard out hijacking
_thread_local = threading.local()

class ThreadLocalStdout:
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout

    def write(self, data):
        self.original_stdout.write(data)
        if getattr(_thread_local, "capture_buffer", None) is not None:
            _thread_local.capture_buffer.write(data)

    def flush(self):
        self.original_stdout.flush()

# Replace sys.stdout once at startup
sys.stdout = ThreadLocalStdout(sys.stdout)

@contextmanager
def capture_logs():
    _thread_local.capture_buffer = io.StringIO()
    try:
        yield _thread_local.capture_buffer
    finally:
        _thread_local.capture_buffer = None

def safe_print(*args, **kwargs):
    """Print that won't crash on Windows cp1252 when LLM output has exotic Unicode."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(a) for a in args)
        print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"), **kwargs)

app = FastAPI(title="FeedToRead Service - Plan A")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include MongoDB-backed routers (auth, sources, newspaper) ────────────────
app.include_router(auth_router)
app.include_router(sources_router)
app.include_router(mongo_newspaper_router)

@app.on_event("startup")
async def startup_event():
    # Existing: check AI models available (sync — run in threadpool implicitly)
    check_models_available()
    # New: connect to MongoDB Atlas and initialise Beanie
    await init_mongo([User, Source, Edition, UserStoryStatusMongo])

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo()

class IngestRequest(BaseModel):
    source_type: str
    source_name: str
    source_url: str
    title: Optional[str] = None
    content: str
    published_at: Optional[str] = None
    fetched_at: Optional[str] = None
    force: Optional[bool] = False

class MarkReadRequest(BaseModel):
    user_id: str
    story_id: int

@app.post("/ingest")
def ingest_endpoint(req: IngestRequest, db: Session = Depends(get_db)):
    _thread_local.capture_buffer = io.StringIO()
    # 1. Content Parser
    cleaned_content = parse_content(req.content)
    
    if not is_meaningful_content(cleaned_content):
        return {"status": "skipped", "reason": "Content not meaningful/too short", "trace": _thread_local.capture_buffer.getvalue()}
        
    content_hash = compute_content_hash(cleaned_content)
    
    # 2. Exact-duplicate check
    existing = db.query(ContentItem).filter(ContentItem.content_hash == content_hash).first()
    if existing and not req.force:
        return {"status": "skipped", "reason": "Exact duplicate content hash", "trace": _thread_local.capture_buffer.getvalue()}
        
    now = datetime.utcnow()
    pub_at = datetime.fromisoformat(req.published_at.replace("Z", "+00:00")).replace(tzinfo=None) if req.published_at else None
    fetch_at = datetime.fromisoformat(req.fetched_at.replace("Z", "+00:00")).replace(tzinfo=None) if req.fetched_at else now

    content_item = ContentItem(
        source_name=req.source_name,
        source_type=req.source_type,
        source_url=req.source_url,
        title=req.title,
        raw_content=cleaned_content,
        content_hash=content_hash,
        published_at=pub_at,
        fetched_at=fetch_at
    )
    db.add(content_item)
    db.commit()  # Commit immediately to release write lock before slow LLM calls
    db.refresh(content_item)  # Re-attach to session with ID
    
    safe_print(f"Calling LLM 1 for content_hash: {content_hash}")
    # 3. LLM 1
    llm1_res = summarize_content(cleaned_content)
    safe_print(f"LLM 1 returned: {llm1_res.get('_status', 'success')}")
    
    if llm1_res.get("_status") == "failed":
        content_item.processing_status = "failed"
        db.commit()
        return {"status": "failed", "reason": "LLM 1 API error", "trace": _thread_local.capture_buffer.getvalue()}
        
    content_item.processing_status = "processed"
    
    is_news = llm1_res.get("is_news", False)
    if req.source_type.upper() == "YOUTUBE":
        is_news = True  # User explicitly requested all YouTube content to be displayed
        
    if not is_news:
        db.commit()
        return {"status": "skipped", "reason": "Not news", "trace": _thread_local.capture_buffer.getvalue()}
        
    summary_item = SummaryItem(
        content_id=content_item.id,
        headline=llm1_res.get("headline", ""),
        summary=llm1_res.get("summary", ""),
        category=llm1_res.get("category", "UNCATEGORIZED"),
        is_news=True,
        event=llm1_res.get("event", ""),
        key_facts=llm1_res.get("key_facts", []),
        stance=llm1_res.get("stance", "NEUTRAL")
    )
    db.add(summary_item)
    db.commit()  # Commit summary before slow LLM 2 call
    db.refresh(summary_item)
    
    # 4. Embed
    emb_text = f"{summary_item.headline} {summary_item.summary}"
    new_embedding = generate_embedding(emb_text)
    
    safe_print("\n========== STAGE: EMBEDDING ==========")
    safe_print(f"Embedding Item: {summary_item.headline}")
    safe_print(f"Vector Dimensions: {len(new_embedding)} dimensions")
    safe_print(f"Vector Preview: [{', '.join(f'{x:.4f}' for x in new_embedding[:8])}, ...] ({len(new_embedding)} dims)")
    safe_print("======================================\n")
    
    # 5. Candidate retrieval (Top-K=5)
    freshness_limit = now - timedelta(hours=48)
    active_groups = db.query(StoryGroup).filter(StoryGroup.updated_at >= freshness_limit).all()
    
    candidates = []
    if active_groups:
        group_embs = [json.loads(g.embedding) for g in active_groups if g.embedding]
        valid_groups = [g for g in active_groups if g.embedding]
        
        if valid_groups:
            sims = cosine_similarity([new_embedding], group_embs)[0]
            all_indices = np.argsort(sims)[::-1]
            top_k_indices = all_indices[:5]
            
            safe_print("\n========== STAGE: CANDIDATE RETRIEVAL ==========")
            safe_print(f"New Item: {summary_item.headline}")
            safe_print(f"Searching against {len(valid_groups)} active stories within the 48h window")
            
            for i, idx in enumerate(all_indices):
                g = valid_groups[idx]
                score = float(sims[idx])
                marker = " -> TOP 5 SENT TO LLM 2" if i < 5 else ""
                safe_print(f"  {score:.4f} - {g.headline}{marker}")
                
                if i < 5:
                    candidates.append({
                        "id": g.id,
                        "headline": g.headline,
                        "summary": g.summary,
                        "event": "N/A (Group)",
                        "category": g.category
                    })
            safe_print("================================================\n")
                
    # 6. LLM 2
    new_item_dict = {
        "id": "new",
        "headline": summary_item.headline,
        "summary": summary_item.summary,
        "event": summary_item.event,
        "category": summary_item.category,
        "key_facts": summary_item.key_facts,
        "stance": "NEUTRAL"
    }
    
    if not candidates:
        llm2_res = {
            "decision": "separate",
            "target_group_id": None,
            "has_conflict": False,
            "final_headline": summary_item.headline,
            "final_summary": summary_item.summary,
            "category": summary_item.category,
            "stance": summary_item.stance or "NEUTRAL"
        }
    else:
        llm2_res = merge_decision(new_item_dict, candidates)
    
    if llm2_res.get("_status") == "failed":
        content_item.processing_status = "failed_llm2"
        db.commit()
        return {"status": "failed", "reason": "LLM 2 API error"}
        
    decision = llm2_res.get("decision", "separate")
    target_id = llm2_res.get("target_group_id")
    
    final_group = None
    if decision == "merge" and target_id:
        final_group = db.query(StoryGroup).filter(StoryGroup.id == int(target_id)).first()
        
    if final_group:
        # Update existing
        final_group.headline = llm2_res.get("final_headline", final_group.headline)
        final_group.summary = llm2_res.get("final_summary", final_group.summary)
        final_group.category = llm2_res.get("category", final_group.category)
        final_group.stance = llm2_res.get("stance", final_group.stance)
        final_group.updated_at = now
        
        # Re-embed
        new_grp_emb = generate_embedding(f"{final_group.headline} {final_group.summary}")
        final_group.embedding = json.dumps(new_grp_emb)
        safe_print("\n========== STAGE: EMBEDDING (GROUP UPDATE) ==========")
        safe_print(f"Embedding Group: {final_group.headline}")
        safe_print(f"Vector Dimensions: {len(new_grp_emb)} dimensions")
        safe_print(f"Vector Preview: [{', '.join(f'{x:.4f}' for x in new_grp_emb[:8])}, ...] ({len(new_grp_emb)} dims)")
        safe_print("=====================================================\n")
    else:
        # separate or new_group
        final_group = StoryGroup(
            headline=llm2_res.get("final_headline", summary_item.headline),
            summary=llm2_res.get("final_summary", summary_item.summary),
            category=llm2_res.get("category", summary_item.category),
            stance=llm2_res.get("stance", "NEUTRAL"),
            embedding=json.dumps(new_embedding)
        )
        db.add(final_group)
        db.flush()
        
    # Link source
    story_source = StorySource(
        story_id=final_group.id,
        content_id=content_item.id,
        source_name=content_item.source_name,
        source_url=content_item.source_url,
        source_type=content_item.source_type
    )
    db.add(story_source)
    db.flush()
    
    # 7. Importance Ranking
    recompute_importance_ranking(db)
    
    db.commit()
    
    trace_logs = _thread_local.capture_buffer.getvalue()
    return {"status": "success", "story_group_id": final_group.id, "decision": decision, "trace": trace_logs}

@app.post("/retry-failed")
def retry_failed(db: Session = Depends(get_db)):
    failed_items_llm1 = db.query(ContentItem).filter(ContentItem.processing_status == "failed").all()
    failed_items_llm2 = db.query(ContentItem).filter(ContentItem.processing_status == "failed_llm2").all()
    
    results = {"retried_llm1": len(failed_items_llm1), "success_llm1": 0, "still_failed_llm1": 0, 
               "retried_llm2": len(failed_items_llm2), "success_llm2": 0, "still_failed_llm2": 0}
               
    failed_items = failed_items_llm1 + failed_items_llm2
    
    for item in failed_items:
        if item.processing_status == "failed":
            # Re-run LLM 1
            llm1_res = summarize_content(item.raw_content)
            
            if llm1_res.get("_status") == "failed":
                results["still_failed_llm1"] += 1
                continue
                
            if not llm1_res.get("is_news", False):
                item.processing_status = "processed"
                db.commit()
                continue
                
            summary_item = SummaryItem(
                content_id=item.id,
                headline=llm1_res.get("headline", ""),
                summary=llm1_res.get("summary", ""),
                category=llm1_res.get("category", "UNCATEGORIZED"),
                is_news=True,
                event=llm1_res.get("event", ""),
                key_facts=llm1_res.get("key_facts", []),
                stance=llm1_res.get("stance", "NEUTRAL")
            )
            db.add(summary_item)
            db.flush()
        else:
            # It's failed_llm2, skip LLM 1
            summary_item = db.query(SummaryItem).filter(SummaryItem.content_id == item.id).first()
            if not summary_item:
                continue
        
        # 4. Embed
        emb_text = f"{summary_item.headline} {summary_item.summary}"
        new_embedding = generate_embedding(emb_text)
        
        # 5. Candidate retrieval
        now = datetime.utcnow()
        freshness_limit = now - timedelta(hours=48)
        active_groups = db.query(StoryGroup).filter(StoryGroup.updated_at >= freshness_limit).all()
        
        candidates = []
        if active_groups:
            group_embs = [json.loads(g.embedding) for g in active_groups if g.embedding]
            valid_groups = [g for g in active_groups if g.embedding]
            
            if valid_groups:
                sims = cosine_similarity([new_embedding], group_embs)[0]
                top_k_indices = np.argsort(sims)[-5:][::-1]
                
                for idx in top_k_indices:
                    g = valid_groups[idx]
                    candidates.append({
                        "id": g.id,
                        "headline": g.headline,
                        "summary": g.summary,
                        "event": "N/A (Group)",
                        "category": g.category
                    })
                    
        # 6. LLM 2
        new_item_dict = {
            "id": "new",
            "headline": summary_item.headline,
            "summary": summary_item.summary,
            "event": summary_item.event,
            "category": summary_item.category,
            "key_facts": summary_item.key_facts,
            "stance": getattr(summary_item, "stance", "NEUTRAL") or "NEUTRAL"
        }
        
        if not candidates:
            llm2_res = {
                "decision": "separate",
                "target_group_id": None,
                "has_conflict": False,
                "final_headline": summary_item.headline,
                "final_summary": summary_item.summary,
                "category": summary_item.category,
                "stance": getattr(summary_item, "stance", "NEUTRAL") or "NEUTRAL"
            }
        else:
            llm2_res = merge_decision(new_item_dict, candidates)
        
        if llm2_res.get("_status") == "failed":
            if item.processing_status == "failed":
                item.processing_status = "failed_llm2"
                db.commit()
                results["still_failed_llm1"] += 1
            else:
                results["still_failed_llm2"] += 1
            continue
            
        if item.processing_status == "failed":
            results["success_llm1"] += 1
        else:
            results["success_llm2"] += 1
            
        item.processing_status = "processed"
        decision = llm2_res.get("decision", "separate")
        target_id = llm2_res.get("target_group_id")
        
        final_group = None
        if decision == "merge" and target_id:
            final_group = db.query(StoryGroup).filter(StoryGroup.id == int(target_id)).first()
            
        if final_group:
            final_group.headline = llm2_res.get("final_headline", final_group.headline)
            final_group.summary = llm2_res.get("final_summary", final_group.summary)
            final_group.category = llm2_res.get("category", final_group.category)
            final_group.stance = llm2_res.get("stance", final_group.stance)
            final_group.updated_at = now
            new_grp_emb = generate_embedding(f"{final_group.headline} {final_group.summary}")
            final_group.embedding = json.dumps(new_grp_emb)
        else:
            final_group = StoryGroup(
                headline=llm2_res.get("final_headline", summary_item.headline),
                summary=llm2_res.get("final_summary", summary_item.summary),
                category=llm2_res.get("category", summary_item.category),
                stance=llm2_res.get("stance", "NEUTRAL"),
                embedding=json.dumps(new_embedding)
            )
            db.add(final_group)
            db.flush()
            
        story_source = StorySource(
            story_id=final_group.id,
            content_id=item.id,
            source_name=item.source_name,
            source_url=item.source_url,
            source_type=item.source_type
        )
        db.add(story_source)
        
    recompute_importance_ranking(db)
    db.commit()
    return results

@app.get("/health")
def health():
    return {"status": "ok"}
