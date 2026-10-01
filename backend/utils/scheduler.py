import os
import subprocess
import sys
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from db.mongo_models import StorySourceMongo, StoryGroupMongo
from db.mongo_models import User, Source
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict
import asyncio

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_cycle, 'interval', hours=5)
    scheduler.start()
    print("Background scheduler started (runs every 5 hours)")

def run_cycle():
    print("[Scheduler] Starting scheduled background extraction cycle...")
    try:
        asyncio.run(_run_cycle_async())
    except Exception as e:
        print(f"[Scheduler] Error in cycle: {e}")

async def _run_cycle_async():
    users = await User.find_all().to_list()
    sources = await Source.find({"isActive": True}).to_list()
    
    # Mapping of source_name (lowercase) -> set of User objects
    source_to_users = defaultdict(set)
    user_map = {u.id: u for u in users}
    
    for s in sources:
        u = user_map.get(s.userId)
        if u:
            source_to_users[s.sourceName.lower()].add((u.email, u.name))
            
    print(f"[Scheduler] Built mapping for {len(source_to_users)} active sources.")
            
    backend_dir = Path(__file__).parent.parent.resolve()
    yt_script = backend_dir / "youtube_extractor" / "main.py"
    rss_script = backend_dir / "rss_extractor" / "main.py"
    env = dict(os.environ, PYTHONPATH=str(backend_dir))
    
    print("[Scheduler] Running youtube_extractor...")
    subprocess.run([sys.executable, str(yt_script)], cwd=str(backend_dir), env=env)
    
    print("[Scheduler] Running rss_extractor...")
    subprocess.run([sys.executable, str(rss_script)], cwd=str(backend_dir), env=env)
    
    print("[Scheduler] Extractors finished. Sending notifications...")
    await send_notifications(source_to_users)

def await send_notifications(source_to_users):
    db = SessionLocal()
    try:
        # Find all un-emailed, genuinely new contributions
        new_sources = db.query(StorySource).filter(
            StorySource.is_new_contribution == True,
            StorySource.emailed == False
        ).all()
        
        if not new_sources:
            print("[Scheduler] No new contributions to notify about.")
            return
            
        # Group new stories by User
        # user -> list of dicts with story info
        user_notifications = defaultdict(list)
        user_objects = {}
        
        # Track which StorySources we process to mark them as emailed later
        processed_source_ids = []
        
        # A single StoryGroup might have multiple new_sources. We want to notify about the StoryGroup once per user.
        # But we also want to batch by user.
        for src in new_sources:
            source_name_lower = src.source_name.lower()
            subscribers = source_to_users.get(source_name_lower, set())
            
            from beanie import PydanticObjectId
            group = await StoryGroupMongo.get(src.story_id)
            if not group:
                continue
                
            story_info = {
                "headline": group.headline,
                "category": group.category,
                "source_name": src.source_name,
                "source_url": src.source_url,
                "group_id": str(group.id)
            }
            
            for email, name in subscribers:
                user_notifications[email].append(story_info)
                user_objects[email] = {'email': email, 'name': name}
                
            processed_source_ids.append(src.id)
            
        # Send emails
        smtp_host = os.environ.get("SMTP_HOST")
        smtp_port = os.environ.get("SMTP_PORT")
        smtp_user = os.environ.get("SMTP_USER")
        smtp_pass = os.environ.get("SMTP_PASSWORD")
        
        if not smtp_host:
            print("[Scheduler] SMTP not configured. Skipping email send.")
        else:
            try:
                server = smtplib.SMTP(smtp_host, int(smtp_port or 587))
                server.starttls()
                server.login(smtp_user, smtp_pass)
                
                for email, stories in user_notifications.items():
                    user = user_objects[email]
                    # Deduplicate stories by group_id in case a user is subscribed to multiple sources
                    # that contributed to the SAME story group
                    unique_stories = {s["group_id"]: s for s in stories}.values()
                    
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = f"FeedToRead: You have {len(unique_stories)} new stories from your subscriptions"
                    msg["From"] = smtp_user
                    msg["To"] = user['email']
                    
                    text_body = f"Hello {user['name']},\n\nYou have {len(unique_stories)} genuinely new stories:\n\n"
                    html_body = f"<html><body><h3>Hello {user['name']},</h3><p>You have {len(unique_stories)} genuinely new stories from your subscriptions:</p><ul>"
                    
                    for s in unique_stories:
                        text_body += f"- [{s['category']}] {s['headline']} (Source: {s['source_name']})\n"
                        html_body += f"<li><b>[{s['category']}]</b> <a href='{s['source_url']}'>{s['headline']}</a> (Source: {s['source_name']})</li>"
                        
                    html_body += "</ul></body></html>"
                    
                    msg.attach(MIMEText(text_body, "plain"))
                    msg.attach(MIMEText(html_body, "html"))
                    
                    server.sendmail(smtp_user, user['email'], msg.as_string())
                    print(f"[Scheduler] Sent email to {user['email']} with {len(unique_stories)} stories.")
                    
                server.quit()
            except Exception as e:
                print(f"[Scheduler] Failed to send emails: {e}")
                
        # Mark as emailed regardless of SMTP success (so we don't retry endlessly if SMTP is broken)
        # "an email failure must never block or fail the ingestion pipeline; log and continue"
        if processed_source_ids:
            db.query(StorySource).filter(StorySource.id.in_(processed_source_ids)).update({"emailed": True}, synchronize_session=False)
            db.commit()
            
    finally:
        db.close()
