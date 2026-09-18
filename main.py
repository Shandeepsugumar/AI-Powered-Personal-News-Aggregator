from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import json
import sys

from database import get_db, ContentItem, SummaryItem, StoryGroup, StorySource, UserStoryStatus, EditionState
from content_parser import parse_content, compute_content_hash, is_meaningful_content
from ai_service import summarize_content, generate_embedding, merge_decision, check_models_available
from ranking import recompute_importance_ranking

def safe_print(*args, **kwargs):
    """Print that won't crash on Windows cp1252 when LLM output has exotic Unicode."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(a) for a in args)
        print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"), **kwargs)

app = FastAPI(title="FeedToRead Service - Plan A")

@app.on_event("startup")
def startup_event():
    check_models_available()

class IngestRequest(BaseModel):
    source_type: str
    source_name: str
    source_url: str
    title: Optional[str] = None
    content: str
    published_at: Optional[str] = None
    fetched_at: Optional[str] = None

class MarkReadRequest(BaseModel):
    user_id: str
    story_id: int

@app.post("/ingest")
def ingest_endpoint(req: IngestRequest, db: Session = Depends(get_db)):
    # 1. Content Parser
    cleaned_content = parse_content(req.content)
    
    if not is_meaningful_content(cleaned_content):
        return {"status": "skipped", "reason": "Content not meaningful/too short"}
        
    content_hash = compute_content_hash(cleaned_content)
    
    # 2. Exact-duplicate check
    existing = db.query(ContentItem).filter(ContentItem.content_hash == content_hash).first()
    if existing:
        return {"status": "skipped", "reason": "Exact duplicate content hash"}
        
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
        return {"status": "failed", "reason": "LLM 1 API error"}
        
    content_item.processing_status = "processed"
    if not llm1_res.get("is_news", False):
        db.commit()
        return {"status": "skipped", "reason": "Not news"}
        
    summary_item = SummaryItem(
        content_id=content_item.id,
        headline=llm1_res.get("headline", ""),
        summary=llm1_res.get("summary", ""),
        category=llm1_res.get("category", "UNCATEGORIZED"),
        is_news=True,
        event=llm1_res.get("event", ""),
        key_facts=llm1_res.get("key_facts", [])
    )
    db.add(summary_item)
    db.commit()  # Commit summary before slow LLM 2 call
    db.refresh(summary_item)
    
    # 4. Embed
    emb_text = f"{summary_item.headline} {summary_item.summary}"
    new_embedding = generate_embedding(emb_text)
    
    # 5. Candidate retrieval (Top-K=5)
    freshness_limit = now - timedelta(hours=48)
    active_groups = db.query(StoryGroup).filter(StoryGroup.updated_at >= freshness_limit).all()
    
    candidates = []
    safe_print("\n--- VERBOSE LOG: NEW ITEM ---")
    safe_print(f"Headline: {summary_item.headline}")
    safe_print("-----------------------------\n")
    
    if active_groups:
        group_embs = [json.loads(g.embedding) for g in active_groups if g.embedding]
        valid_groups = [g for g in active_groups if g.embedding]
        
        if valid_groups:
            sims = cosine_similarity([new_embedding], group_embs)[0]
            top_k_indices = np.argsort(sims)[-5:][::-1]
            
            safe_print("--- VERBOSE LOG: TOP-K CANDIDATES ---")
            for idx in top_k_indices:
                g = valid_groups[idx]
                score = float(sims[idx])
                safe_print(f"Candidate ID {g.id}: Score={score:.4f} | Headline: {g.headline}")
                candidates.append({
                    "id": g.id,
                    "headline": g.headline,
                    "summary": g.summary,
                    "event": "N/A (Group)",
                    "category": g.category
                })
            safe_print("-------------------------------------\n")
                
    # 6. LLM 2
    new_item_dict = {
        "id": "new",
        "headline": summary_item.headline,
        "summary": summary_item.summary,
        "event": summary_item.event,
        "category": summary_item.category,
        "key_facts": summary_item.key_facts
    }
    
    llm2_res = merge_decision(new_item_dict, candidates)
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
    return {"status": "success", "story_group_id": final_group.id, "decision": decision}

@app.get("/newspaper")
def newspaper_endpoint(user_id: str, db: Session = Depends(get_db)):
    # Edition Tracking
    ed_state = db.query(EditionState).filter(EditionState.user_id == user_id).first()
    if not ed_state:
        ed_state = EditionState(user_id=user_id, current_edition_number=1)
        db.add(ed_state)
    else:
        ed_state.current_edition_number += 1
    db.commit()
    
    now = datetime.utcnow()
    freshness_limit = now - timedelta(hours=48)
    
    groups = db.query(StoryGroup).filter(StoryGroup.updated_at >= freshness_limit).all()
    
    stories = []
    for g in groups:
        sources_list = []
        for s in g.sources:
            sources_list.append({
                "name": s.source_name,
                "url": s.source_url,
                "type": s.source_type.upper()
            })
            
        stories.append({
            "id": str(g.id),
            "headline": g.headline,
            "category": g.category.upper(),
            "stance": f"{g.stance} STANCE" if g.stance else "NEUTRAL STANCE",
            "importance": g.importance or "minor",
            "summary": g.summary,
            "sources": sources_list,
            "timestamp": g.updated_at.isoformat() + "Z"
        })
        
    return {
        "_id": f"edition_{user_id}",
        "editionNumber": ed_state.current_edition_number,
        "dateString": now.strftime("%Y-%m-%d"),
        "createdAt": now.isoformat() + "Z",
        "stories": stories
    }

@app.post("/mark_read")
def mark_read(req: MarkReadRequest, db: Session = Depends(get_db)):
    status = db.query(UserStoryStatus).filter(
        UserStoryStatus.user_id == req.user_id,
        UserStoryStatus.story_id == req.story_id
    ).first()
    
    if not status:
        status = UserStoryStatus(user_id=req.user_id, story_id=req.story_id)
        db.add(status)
        
    status.read_at = datetime.utcnow()
    db.commit()
    return {"status": "success"}

@app.post("/retry-failed")
def retry_failed(db: Session = Depends(get_db)):
    failed_items = db.query(ContentItem).filter(ContentItem.processing_status == "failed").all()
    results = {"retried": len(failed_items), "success": 0, "still_failed": 0}
    
    for item in failed_items:
        # Re-run LLM 1
        llm1_res = summarize_content(item.raw_content)
        
        if llm1_res.get("_status") == "failed":
            results["still_failed"] += 1
            continue
            
        # Success!
        item.processing_status = "processed"
        results["success"] += 1
        
        if not llm1_res.get("is_news", False):
            continue
            
        summary_item = SummaryItem(
            content_id=item.id,
            headline=llm1_res.get("headline", ""),
            summary=llm1_res.get("summary", ""),
            category=llm1_res.get("category", "UNCATEGORIZED"),
            is_news=True,
            event=llm1_res.get("event", ""),
            key_facts=llm1_res.get("key_facts", [])
        )
        db.add(summary_item)
        db.flush()
        
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
            "key_facts": summary_item.key_facts
        }
        
        llm2_res = merge_decision(new_item_dict, candidates)
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
