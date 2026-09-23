import requests
import time
import sys

# wait for server
for i in range(30):
    try:
        r = requests.get("http://localhost:8000/health")
        if r.status_code == 200:
            print("Server is up!")
            break
    except Exception:
        pass
    time.sleep(1)
else:
    print("Server failed to start in time!")
    sys.exit(1)

def test_ingest(headline, summary, source_name):
    payload = {
        "source_name": source_name,
        "source_type": "rss",
        "source_url": f"http://test.com/{source_name}",
        "title": headline,
        "content": f"{headline}. {summary}"
    }
    r = requests.post("http://localhost:8000/ingest", json=payload)
    print(f"[{source_name}] Ingest response: {r.json()}")

# Story 1: Extremely Positive Scientific Breakthrough
test_ingest("New Cure for Cancer Discovered", "Scientists have made a miraculous breakthrough, finding a complete cure for all types of cancer with zero side effects. This is the greatest medical achievement in human history.", "ScienceDaily")

# Story 2: Extremely Negative Disaster Report
test_ingest("Massive Earthquake Destroys City", "A devastating magnitude 9 earthquake has completely leveled the city, leaving thousands missing and causing billions in catastrophic damages.", "DisasterNews")

r = requests.get("http://localhost:8000/newspaper?user_id=test_user")
for story in r.json().get("active_stories", []):
    print(f"Headline: {story['headline']} | Stance: {story['stance']}")
