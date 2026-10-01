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

from utils.content_parser import parse_content, compute_content_hash, is_meaningful_content
from ai_agent.ai_service import summarize_content, generate_embedding, merge_decision, check_models_available
from utils.ranking import recompute_importance_ranking
from db.mongo_db import init_mongo, close_mongo
from db.mongo_models import User, Source, Edition, UserStoryStatusMongo, ContentItemMongo, SummaryItemMongo, StoryGroupMongo, StorySourceMongo
from utils.scheduler import start_scheduler

from api.mongo_auth import router as auth_router
from api.mongo_sources import router as sources_router
from api.mongo_newspaper import router as mongo_newspaper_router
import io
import threading
_thread_local = threading.local()
import threading
from contextlib import contextmanager



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
    check_models_available()
    start_scheduler()
    # New: connect to MongoDB Atlas and initialise Beanie
    await init_mongo([User, Source, Edition, UserStoryStatusMongo, ContentItemMongo, SummaryItemMongo, StoryGroupMongo, StorySourceMongo])

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo()

class IngestRequest(BaseModel):
    source_type: str
    source_name: str
    source_url: str
    title: Optional[str] = None
    content: str
    image_url: Optional[str] = None
    published_at: Optional[str] = None
    fetched_at: Optional[str] = None
    force: Optional[bool] = False

class MarkReadRequest(BaseModel):
    user_id: str
    story_id: int

@app.post("/ingest")
async def ingest_endpoint(req: IngestRequest):
    try:
        _thread_local.capture_buffer = io.StringIO()
        cleaned_content = parse_content(req.content)
    
        if not is_meaningful_content(cleaned_content):
            return {"status": "skipped", "reason": "Content not meaningful/too short", "trace": _thread_local.capture_buffer.getvalue()}
        
        content_hash = compute_content_hash(cleaned_content)
    
        existing = await ContentItemMongo.find_one(ContentItemMongo.content_hash == content_hash)
        if existing and not req.force:
            return {"status": "skipped", "reason": "Exact duplicate content hash", "trace": _thread_local.capture_buffer.getvalue()}
        
        now = datetime.utcnow()
        pub_at = datetime.fromisoformat(req.published_at.replace("Z", "+00:00")).replace(tzinfo=None) if req.published_at else None
        fetch_at = datetime.fromisoformat(req.fetched_at.replace("Z", "+00:00")).replace(tzinfo=None) if req.fetched_at else now

        content_item = ContentItemMongo(
            source_name=req.source_name,
            source_type=req.source_type,
            source_url=req.source_url,
            title=req.title,
            raw_content=cleaned_content,
            image_url=req.image_url,
            content_hash=content_hash,
            published_at=pub_at,
            fetched_at=fetch_at
        )
        await content_item.insert()
    
        safe_print(f"Calling LLM 1 for content_hash: {content_hash}")
        from starlette.concurrency import run_in_threadpool
        llm1_res = await run_in_threadpool(summarize_content, cleaned_content)
        safe_print(f"LLM 1 returned: {llm1_res.get('_status', 'success')}")
    
        if llm1_res.get("_status") == "failed":
            content_item.processing_status = "failed"
            await content_item.save()
            return {"status": "failed", "reason": "LLM 1 API error", "trace": _thread_local.capture_buffer.getvalue()}
        
        content_item.processing_status = "processed"
        await content_item.save()
    
        is_news = llm1_res.get("is_news", False)
        if req.source_type.upper() == "YOUTUBE":
            is_news = True
        
        if not is_news:
            return {"status": "skipped", "reason": "Not news", "trace": _thread_local.capture_buffer.getvalue()}
        
        summary_item = SummaryItemMongo(
            content_id=content_item.id,
            headline=llm1_res.get("headline", ""),
            summary=llm1_res.get("summary", ""),
            category=llm1_res.get("category", "UNCATEGORIZED"),
            is_news=True,
            event=llm1_res.get("event", ""),
            key_facts=llm1_res.get("key_facts", []),
            stance=llm1_res.get("stance", "NEUTRAL")
        )
        await summary_item.insert()
    
        emb_text = f"{summary_item.headline} {summary_item.summary}"
        new_embedding = await run_in_threadpool(generate_embedding, emb_text)
    
        safe_print("
========== STAGE: EMBEDDING ==========")
        safe_print(f"Embedding Item: {summary_item.headline}")
        safe_print(f"Vector Dimensions: {len(new_embedding)} dimensions")
        safe_print(f"Vector Preview: [{', '.join(f'{x:.4f}' for x in new_embedding[:8])}, ...] ({len(new_embedding)} dims)")
        safe_print("======================================
")
    
        freshness_limit = now - timedelta(hours=48)
        active_groups = await StoryGroupMongo.find(StoryGroupMongo.updated_at >= freshness_limit).to_list()
    
        candidates = []
        if active_groups:
            group_embs = [g.embedding for g in active_groups if g.embedding]
            valid_groups = [g for g in active_groups if g.embedding]
        
            if valid_groups:
                from utils.content_parser import cosine_similarity
                import numpy as np
                sims = cosine_similarity([new_embedding], group_embs)[0]
                all_indices = np.argsort(sims)[::-1]
                top_k_indices = all_indices[:5]
            
                safe_print("
========== STAGE: CANDIDATE RETRIEVAL ==========")
                safe_print(f"New Item: {summary_item.headline}")
                safe_print(f"Searching against {len(valid_groups)} active stories within the 48h window")
            
                for i, idx in enumerate(all_indices):
                    g = valid_groups[idx]
                    score = float(sims[idx])
                    marker = " -> TOP 5 SENT TO LLM 2" if i < 5 else ""
                    safe_print(f"  {score:.4f} - {g.headline}{marker}")
                
                    if i < 5:
                        candidates.append({
                            "id": str(g.id),
                            "headline": g.headline,
                            "summary": g.summary,
                            "event": "N/A (Group)",
                            "category": g.category
                        })
                safe_print("================================================
")
                
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
            llm2_res = await run_in_threadpool(merge_decision, new_item_dict, candidates)
    
        if llm2_res.get("_status") == "failed":
            content_item.processing_status = "failed_llm2"
            await content_item.save()
            return {"status": "failed", "reason": "LLM 2 API error"}
        
        decision = llm2_res.get("decision", "separate")
        target_id = llm2_res.get("target_group_id")
    
        final_group = None
        if decision == "merge" and target_id:
            from beanie import PydanticObjectId
            final_group = await StoryGroupMongo.get(PydanticObjectId(target_id))
        
        if final_group:
            final_group.headline = llm2_res.get("final_headline", final_group.headline)
            final_group.summary = llm2_res.get("final_summary", final_group.summary)
            final_group.category = llm2_res.get("category", final_group.category)
            final_group.stance = llm2_res.get("stance", final_group.stance)
            if not final_group.image_url and content_item.image_url:
                final_group.image_url = content_item.image_url
            final_group.updated_at = now
        
            new_grp_emb = await run_in_threadpool(generate_embedding, f"{final_group.headline} {final_group.summary}")
            final_group.embedding = new_grp_emb
            safe_print("
========== STAGE: EMBEDDING (GROUP UPDATE) ==========")
            safe_print(f"Embedding Group: {final_group.headline}")
            safe_print(f"Vector Dimensions: {len(new_grp_emb)} dimensions")
            safe_print(f"Vector Preview: [{', '.join(f'{x:.4f}' for x in new_grp_emb[:8])}, ...] ({len(new_grp_emb)} dims)")
            safe_print("=====================================================
")
            await final_group.save()
        else:
            final_group = StoryGroupMongo(
                headline=llm2_res.get("final_headline", summary_item.headline),
                summary=llm2_res.get("final_summary", summary_item.summary),
                category=llm2_res.get("category", summary_item.category),
                stance=llm2_res.get("stance", "NEUTRAL"),
                image_url=content_item.image_url,
                embedding=new_embedding
            )
            await final_group.insert()
        
        is_new_info = False
        if decision in ("new_group", "separate"):
            is_new_info = True
        elif decision == "merge" and final_group:
            if llm2_res.get("has_conflict", False):
                is_new_info = True
            else:
                existing_sources = await StorySourceMongo.find(StorySourceMongo.story_id == final_group.id).to_list()
                existing_names = [s.source_name for s in existing_sources]
                if content_item.source_name not in existing_names:
                    is_new_info = True

        story_source = StorySourceMongo(
            story_id=final_group.id,
            content_id=content_item.id,
            source_name=content_item.source_name,
            source_url=content_item.source_url,
            source_type=content_item.source_type,
            is_new_contribution=is_new_info,
            emailed=False
        )
        await story_source.insert()
    
        await recompute_importance_ranking()
    
        trace_logs = _thread_local.capture_buffer.getvalue()
        return {"status": "success", "story_group_id": str(final_group.id), "decision": decision, "trace": trace_logs}

    except Exception as e:
        import traceback
        return {"status": "500_error", "traceback": traceback.format_exc()}

@app.post("/retry-failed")
async def retry_failed():
    failed_items_llm1 = await ContentItemMongo.find(ContentItemMongo.processing_status == "failed").to_list()
    failed_items_llm2 = await ContentItemMongo.find(ContentItemMongo.processing_status == "failed_llm2").to_list()
    
    results = {"retried_llm1": len(failed_items_llm1), "success_llm1": 0, "still_failed_llm1": 0, 
               "retried_llm2": len(failed_items_llm2), "success_llm2": 0, "still_failed_llm2": 0}
               
    failed_items = failed_items_llm1 + failed_items_llm2
    from starlette.concurrency import run_in_threadpool
    
    for item in failed_items:
        if item.processing_status == "failed":
            llm1_res = await run_in_threadpool(summarize_content, item.raw_content)
            
            if llm1_res.get("_status") == "failed":
                results["still_failed_llm1"] += 1
                continue
                
            if not llm1_res.get("is_news", False):
                item.processing_status = "processed"
                await item.save()
                continue
                
            summary_item = SummaryItemMongo(
                content_id=item.id,
                headline=llm1_res.get("headline", ""),
                summary=llm1_res.get("summary", ""),
                category=llm1_res.get("category", "UNCATEGORIZED"),
                is_news=True,
                event=llm1_res.get("event", ""),
                key_facts=llm1_res.get("key_facts", []),
                stance=llm1_res.get("stance", "NEUTRAL")
            )
            await summary_item.insert()
        else:
            pass
            
    return results

@app.get("/")
@app.get("/health")

@app.get("/debug")
def debug():
    try:
        db = next(get_db())
        count = db.query(ContentItem).count()
        return {"status": "ok", "db_count": count}
    except Exception as e:
        import traceback
        return {"status": "error", "trace": traceback.format_exc()}

def health():
    return {"status": "ok"}
