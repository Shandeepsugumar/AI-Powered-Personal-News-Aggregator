from datetime import datetime
from database import SessionLocal, NewsItem

def cleanup_expired_items():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        expired = db.query(NewsItem).filter(NewsItem.expires_at < now).all()
        count = len(expired)
        if count > 0:
            for item in expired:
                db.delete(item)
            db.commit()
            print(f"Deleted {count} expired items.")
        else:
            print("No expired items to delete.")
    except Exception as e:
        print(f"Error during cleanup: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_expired_items()
