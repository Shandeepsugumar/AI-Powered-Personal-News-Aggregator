import requests
import time

time.sleep(2)

def test_ingest(headline, summary, source_name):
    payload = {
        "source_name": source_name,
        "source_type": "rss",
        "source_url": f"http://test.com/{source_name}",
        "title": headline,
        "raw_content": f"{headline}. {summary}"
    }
    r = requests.post("http://localhost:8000/ingest", json=payload)
    print(f"[{source_name}] Ingest response: {r.text}")

# Story 1: Extremely Positive Scientific Breakthrough
test_ingest("New Cure for Cancer Discovered", "Scientists have made a miraculous breakthrough, finding a complete cure for all types of cancer with zero side effects. This is the greatest medical achievement in human history.", "ScienceDaily")
