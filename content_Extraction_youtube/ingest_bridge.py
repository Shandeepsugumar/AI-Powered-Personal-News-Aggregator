"""
ingest_bridge.py — Bridge between local YouTube transcript extraction and the FeedToRead /ingest API.

Usage:
    # Ingest all new .txt files in the current folder:
    python ingest_bridge.py

    # Ingest a specific video ID (re-ingests even if already sent):
    python ingest_bridge.py yz_RwdHplNk

    # Re-ingest (force, ignores marker file):
    python ingest_bridge.py yz_RwdHplNk --force

    # Point at a different server:
    python ingest_bridge.py --server http://localhost:8000

The script tracks already-sent video IDs in ingested.txt so re-running never
double-posts the same content.
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timezone

# ─── Config ──────────────────────────────────────────────────────────────────

INGEST_URL = "http://localhost:8000/ingest"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MARKER_FILE = os.path.join(SCRIPT_DIR, "ingested.txt")

# ─── Helpers ─────────────────────────────────────────────────────────────────

def safe_print(text):
    """Safely print unicode text to Windows console without crashing."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', errors='replace').decode('ascii'))

def load_ingested():
    """Return set of video IDs already successfully sent to /ingest."""
    if not os.path.exists(MARKER_FILE):
        return set()
    with open(MARKER_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def mark_ingested(video_id):
    """Append a video_id to the marker file."""
    with open(MARKER_FILE, "a", encoding="utf-8") as f:
        f.write(video_id + "\n")


def fetch_metadata_via_ytdlp(video_id):
    """
    Fetch video title, channel name, and upload date using yt-dlp (no download).
    Used as fallback when no sidecar .json exists yet.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        import yt_dlp
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        raw_date = info.get("upload_date", "")
        if raw_date and len(raw_date) == 8:
            published_at = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}T00:00:00Z"
        else:
            published_at = None
        meta = {
            "video_id": video_id,
            "title": info.get("title", ""),
            "channel_name": info.get("uploader") or info.get("channel", ""),
            "published_at": published_at,
            "url": url,
        }
        # Save sidecar so future runs dont need to re-fetch
        sidecar_path = os.path.join(SCRIPT_DIR, f"{video_id}.json")
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f"  [meta] Fetched and saved sidecar: {video_id}.json")
        return meta
    except ImportError:
        print("  [meta] yt-dlp not installed — metadata will be minimal.")
    except Exception as e:
        print(f"  [meta] yt-dlp metadata fetch failed: {e}")
    return {
        "video_id": video_id,
        "title": "",
        "channel_name": "YouTube",
        "published_at": None,
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def load_metadata(video_id):
    """Load sidecar JSON; fall back to live yt-dlp fetch if not found."""
    sidecar_path = os.path.join(SCRIPT_DIR, f"{video_id}.json")
    if os.path.exists(sidecar_path):
        with open(sidecar_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        print(f"  [meta] Loaded sidecar: {video_id}.json")
        return meta
    else:
        print(f"  [meta] No sidecar found — fetching live via yt-dlp...")
        return fetch_metadata_via_ytdlp(video_id)


def load_transcript(video_id):
    """Read transcript text from {video_id}.txt."""
    txt_path = os.path.join(SCRIPT_DIR, f"{video_id}.txt")
    with open(txt_path, "r", encoding="utf-8") as f:
        return f.read()


def build_payload(video_id, transcript, meta):
    """Build the exact /ingest payload from transcript + sidecar metadata."""
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "source_type": "youtube",
        "source_name": meta.get("channel_name") or "YouTube",
        "source_url": meta.get("url") or f"https://www.youtube.com/watch?v={video_id}",
        "title": meta.get("title") or video_id,
        "content": transcript,
        "published_at": meta.get("published_at"),
        "fetched_at": fetched_at,
    }


def ingest_video(video_id, server_url, force=False):
    """
    Full ingest flow for a single video_id.
    Returns True on success (200 from server), False otherwise.
    """
    print(f"\n{'='*60}")
    print(f"Video ID : {video_id}")

    txt_path = os.path.join(SCRIPT_DIR, f"{video_id}.txt")
    if not os.path.exists(txt_path):
        print(f"  [SKIP] No transcript file found: {txt_path}")
        return False

    transcript = load_transcript(video_id)
    meta = load_metadata(video_id)

    safe_print(f"  Title   : {meta.get('title') or '(unknown)'}")
    safe_print(f"  Channel : {meta.get('channel_name') or '(unknown)'}")
    safe_print(f"  Date    : {meta.get('published_at') or '(unknown)'}")
    safe_print(f"  Length  : {len(transcript):,} chars")

    payload = build_payload(video_id, transcript, meta)

    print(f"  POSTing to {server_url} ...")
    try:
        resp = requests.post(server_url, json=payload, timeout=180)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "?")
        decision = data.get("decision", "")
        reason = data.get("reason", "")
        if decision:
            print(f"  [OK] status={status}  decision={decision}")
        else:
            print(f"  [OK] status={status}  reason={reason}")
        return status in ("success", "skipped")
    except requests.exceptions.ConnectionError:
        print(f"  [ERROR] Cannot connect to {server_url}. Is the FastAPI server running?")
        return False
    except requests.exceptions.Timeout:
        print(f"  [ERROR] Request timed out (180s). Server may still be processing — check logs.")
        return False
    except requests.exceptions.HTTPError as e:
        print(f"  [ERROR] HTTP {e.response.status_code}: {e.response.text[:300]}")
        return False
    except Exception as e:
        print(f"  [ERROR] Unexpected: {e}")
        return False


def scan_and_ingest(server_url, force=False):
    """Scan SCRIPT_DIR for all {video_id}.txt files and ingest any not yet sent."""
    already_ingested = load_ingested()
    txt_files = sorted(
        f for f in os.listdir(SCRIPT_DIR)
        if f.endswith(".txt") and f != "ingested.txt"
    )
    video_ids = [os.path.splitext(f)[0] for f in txt_files]

    if not video_ids:
        print("No transcript .txt files found in", SCRIPT_DIR)
        return

    print(f"Found {len(video_ids)} transcript file(s): {', '.join(video_ids)}")
    new_count = 0
    for vid in video_ids:
        if not force and vid in already_ingested:
            print(f"\n[SKIP] {vid} already ingested (in ingested.txt). Use --force to re-ingest.")
            continue
        success = ingest_video(vid, server_url, force)
        if success and vid not in already_ingested:
            mark_ingested(vid)
            new_count += 1

    print(f"\n{'='*60}")
    print(f"Done. {new_count} new video(s) ingested.")


def main():
    parser = argparse.ArgumentParser(
        description="Bridge: POST YouTube transcripts to the FeedToRead /ingest endpoint."
    )
    parser.add_argument(
        "video_id",
        nargs="?",
        default=None,
        help="Specific video ID to ingest. Omit to scan folder for all new .txt files.",
    )
    parser.add_argument(
        "--server",
        default=INGEST_URL,
        help=f"Full /ingest URL (default: {INGEST_URL})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even if already in ingested.txt",
    )
    args = parser.parse_args()

    print("FeedToRead — YouTube Ingest Bridge")
    print("=" * 60)
    print(f"Server : {args.server}")
    print(f"Folder : {SCRIPT_DIR}")

    if args.video_id:
        already = load_ingested()
        if args.video_id in already and not args.force:
            print(f"\n[INFO] {args.video_id} already ingested. Use --force to re-ingest.")
            return
        success = ingest_video(args.video_id, args.server, args.force)
        if success and args.video_id not in already:
            mark_ingested(args.video_id)
    else:
        scan_and_ingest(args.server, args.force)


if __name__ == "__main__":
    main()
