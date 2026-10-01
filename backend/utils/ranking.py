import sys
def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(a) for a in args)
        print(text.encode('ascii', errors='replace').decode('ascii'), **kwargs)

from datetime import datetime, timedelta
from db.mongo_models import StoryGroupMongo, StorySourceMongo

async def recompute_importance_ranking(freshness_hours: int = 48):
    NEWS_CATEGORIES = {"TECHNOLOGY", "BUSINESS", "SPORTS", "POLITICS", "SCIENCE"}
    freshness_threshold = datetime.utcnow() - timedelta(hours=freshness_hours)
    
    active_groups = await StoryGroupMongo.find(
        StoryGroupMongo.updated_at >= freshness_threshold
    ).to_list()
    
    if not active_groups:
        return
        
    news_stats = []
    
    for group in active_groups:
        if group.category.upper() not in NEWS_CATEGORIES:
            group.importance = "feature"
            await group.save()
            continue
            
        # Count distinct source names
        sources = await StorySourceMongo.find(StorySourceMongo.story_id == group.id).to_list()
        source_count = len(set([s.source_name for s in sources]))
        
        news_stats.append({
            "group": group,
            "source_count": source_count,
            "updated_at": group.updated_at
        })
        
    news_stats.sort(key=lambda x: (x["source_count"], x["updated_at"]), reverse=True)
    
    safe_print("\n========== STAGE: IMPORTANCE RANKING ==========")
    safe_print("Ranking Active Story Groups:")
    
    for idx, stat in enumerate(news_stats):
        group = stat["group"]
        source_count = stat["source_count"]
        
        if idx == 0:
            group.importance = "lead"
        elif source_count >= 2:
            group.importance = "major"
        else:
            group.importance = "minor"
            
        await group.save()
        safe_print(f"  - '{group.headline}' | Sources: {source_count} | Updated: {stat['updated_at']} -> {group.importance}")

    safe_print("===============================================\n")
