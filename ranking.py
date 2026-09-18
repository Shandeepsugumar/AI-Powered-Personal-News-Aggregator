from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from database import StoryGroup, StorySource

def recompute_importance_ranking(db: Session, freshness_hours: int = 48):
    """
    Rank all active story_groups (within freshness window) by:
      1. Distinct source count (descending)
      2. Most recent updated_at (tie-breaker)
      
    Assign: 
      Rank 1 -> 'lead'
      source_count >= 2 (excluding lead) -> 'major'
      source_count == 1 -> 'minor'
    """
    freshness_threshold = datetime.utcnow() - timedelta(hours=freshness_hours)
    
    # Get all active story groups
    active_groups = db.query(StoryGroup).filter(
        StoryGroup.updated_at >= freshness_threshold
    ).all()
    
    if not active_groups:
        return
        
    group_stats = []
    for group in active_groups:
        # Count distinct source names in StorySource for this group
        source_count = db.query(StorySource.source_name).filter(
            StorySource.story_id == group.id
        ).distinct().count()
        
        group_stats.append({
            "group": group,
            "source_count": source_count,
            "updated_at": group.updated_at
        })
        
    # Sort by source_count DESC, then updated_at DESC
    group_stats.sort(key=lambda x: (x["source_count"], x["updated_at"]), reverse=True)
    
    # Assign labels
    for idx, stat in enumerate(group_stats):
        group = stat["group"]
        source_count = stat["source_count"]
        
        if idx == 0:
            group.importance = "lead"
        elif source_count >= 2:
            group.importance = "major"
        else:
            group.importance = "minor"
            
    db.commit()
