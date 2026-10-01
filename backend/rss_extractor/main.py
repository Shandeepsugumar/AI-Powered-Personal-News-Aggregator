import os
PORT = os.environ.get("PORT", "8000")
import sys
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

INGEST_URL = f"http://localhost:{PORT}/ingest"
SOURCES_API = f"http://localhost:{PORT}/api/sources/active-targets"

KNOWN_FEEDS = {
    "the hindu": "https://www.thehindu.com/feeder/default/rss/homepage/",
    "times of india": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    "daily thanthi": "https://www.dailythanthi.com/rss/news.xml",
    "the verge": "https://www.theverge.com/rss/index.xml"
}

def fetch_active_sources():
    sources = []
    user_id = os.environ.get("USER_ID")
    try:
        for stype in ["BLOG", "NEWSLETTER", "RSS"]:
            url = f"{SOURCES_API}?type={stype}"
            if user_id:
                url += f"&user_id={user_id}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                targets = resp.json().get("targets", [])
                sources.extend(targets)
    except Exception as e:
        print(f"Error fetching active sources: {e}")
    return sources

def resolve_feed_url(source_name):
    lower_name = source_name.lower().strip()
    if lower_name in KNOWN_FEEDS:
        return KNOWN_FEEDS[lower_name]
    
    if source_name.startswith("http://") or source_name.startswith("https://"):
        url = source_name
    else:
        domain = lower_name.replace(" ", "")
        url = f"https://www.{domain}.com"
        
    print(f"  Trying base URL: {url}")
    try:
        html_resp = requests.get(url, timeout=10)
        html_resp.raise_for_status()
        soup = BeautifulSoup(html_resp.content, "html.parser")
        
        for link in soup.find_all("link", rel="alternate"):
            type_attr = link.get("type", "").lower()
            if "rss+xml" in type_attr or "atom+xml" in type_attr:
                href = link.get("href")
                return urljoin(url, href)
    except Exception:
        pass
        
    for path in ["/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml"]:
        try:
            feed_url = urljoin(url, path)
            resp = requests.get(feed_url, timeout=5)
            if resp.status_code == 200:
                ct = resp.headers.get("Content-Type", "").lower()
                head = resp.text[:100].lower()
                if "xml" in ct or "rss" in head or "xml" in head:
                    return feed_url
        except Exception:
            continue
            
    return None

def get_image_url(entry, html_soup=None):
    # Try entry media_content
    if hasattr(entry, 'media_content'):
        for m in entry.media_content:
            if 'url' in m: return m['url']
    # Try entry enclosures
    if hasattr(entry, 'enclosures'):
        for e in entry.enclosures:
            if 'type' in e and e['type'].startswith('image'): return e['href']
    # Try og:image from soup
    if html_soup:
        og_img = html_soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            return og_img["content"]
    return None

def fetch_full_article(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        
        image_url = None
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            image_url = og_img["content"]
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            element.decompose()
            
        text = soup.get_text(separator="
", strip=True)
        return "
".join([line.strip() for line in text.split("
") if line.strip()]), image_url
    except Exception as e:
        print(f"    Failed to fetch full article from {url}: {e}")
        return "", None

def process_feed(source, feed_url):
    print(f"Fetching feed: {feed_url}")
    
    try:
        # Pass realistic headers in case blogs block standard Python requests
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        # Using requests to check status explicitly before feedparser
        resp = requests.get(feed_url, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"  FETCH FAILED: Network error or non-200 response -> {e}")
        return

    parsed = feedparser.parse(resp.content)
    
    if parsed.bozo and parsed.bozo_exception:
        # bozo=1 means malformed feed, bozo_exception holds the error
        print(f"  FETCH FAILED: Malformed feed -> {parsed.bozo_exception}")
        return
        
    if not parsed.entries:
        print("  NO RECENT ENTRIES: Feed is valid but empty.")
        return
        
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=72)
    
    count = 0
    processed_count = 0
    for entry in parsed.entries:
        if processed_count >= 3:
            break
            
        published_dt = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        
        if published_dt and published_dt < cutoff:
            continue
            
        title = entry.get("title", "")
        link = entry.get("link", "")
        
        content_html = ""
        if hasattr(entry, "content"):
            content_html = entry.content[0].value
        elif hasattr(entry, "summary"):
            content_html = entry.summary
            
        text_content = BeautifulSoup(content_html, "html.parser").get_text(separator="
", strip=True)
        
        image_url = None
        
        # Check media content or enclosures in the feed
        if hasattr(entry, 'media_content'):
            for m in entry.media_content:
                if 'url' in m:
                    image_url = m['url']
                    break
        if not image_url and hasattr(entry, 'enclosures'):
            for e in entry.enclosures:
                if 'type' in e and getattr(e, 'type', '').startswith('image'):
                    image_url = e.get('href')
                    break
        
        if len(text_content) < 500:
            print(f"  [FALLBACK PATH] Content too short ({len(text_content)} chars). Fetching full article: {link}")
            text_content, scraped_img = fetch_full_article(link)
            if not image_url and scraped_img:
                image_url = scraped_img
        else:
            print(f"  [DIRECT PATH] Using feed content directly ({len(text_content)} chars).")
            # If direct path has no image, still fetch article just for the og:image metadata (cheap get request without parsing all text if we just want soup)
            if not image_url:
                _, scraped_img = fetch_full_article(link)
                if scraped_img:
                    image_url = scraped_img
            
        if len(text_content) < 200:
            print(f"  Skipping '{title}' - not enough meaningful content.")
            continue
            
        payload = {
            "source_type": source["sourceType"],
            "source_name": source["sourceName"],
            "source_url": link,
            "title": title,
            "content": text_content,
            "published_at": published_dt.isoformat() if published_dt else None,
            "fetched_at": now.isoformat(),
            "image_url": image_url
        }

        
        print(f"  POSTing '{title}' to /ingest...")
        try:
            resp = requests.post(INGEST_URL, json=payload, timeout=120)
            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                    print(f"    -> [OK] status={data.get('status')} decision={data.get('decision')}")
                except Exception:
                    print(f"    -> [OK] status={resp.status_code}")
            else:
                print(f"    -> [ERROR] POST failed with status: {resp.status_code}, {resp.text}")
        except Exception as e:
            print(f"    -> [ERROR] POST failed: {e}")
            
        processed_count += 1
        
    if processed_count == 0:
        print("  NO RECENT ENTRIES: Entries exist, but none published in the last 72 hours.")

def main():
    print("FeedToRead RSS/Blog Pipeline")
    print("=" * 60)
    
    sources = fetch_active_sources()
    if not sources:
        print("No active BLOG/NEWSLETTER/RSS sources found in backend.")
        return
        
    for source in sources:
        name = source["sourceName"]
        print(f"\nProcessing source: {name} ({source['sourceType']})")
        print("-" * 60)
        
        feed_url = resolve_feed_url(name)
        if not feed_url:
            print(f"  FEED NOT FOUND: Could not resolve feed URL for {name}. Skipping.")
            continue
            
        process_feed(source, feed_url)

if __name__ == "__main__":
    main()
