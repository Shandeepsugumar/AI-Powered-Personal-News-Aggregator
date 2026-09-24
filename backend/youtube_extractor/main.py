import os
PORT = os.environ.get("PORT", "8000")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
import requests
import warnings
import time
import sys
import re
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.formatters import SRTFormatter
import base64
from dotenv import load_dotenv

load_dotenv()

# Reconfigure stdout to support printing emojis and unicode characters on Windows
sys.stdout.reconfigure(encoding='utf-8')

warnings.filterwarnings("ignore")

API_KEY = os.environ.get("YOUTUBE_API_KEY")

def fetch_active_channels():
    try:
        response = requests.get(f"http://localhost:{PORT}/api/sources/active-targets?type=YOUTUBE", timeout=10)
        response.raise_for_status()
        data = response.json()
        return [target["sourceName"] for target in data.get("targets", [])]
    except Exception as e:
        print(f"Error fetching active channels from backend: {e}")
        return []

BASE_URL = "https://www.googleapis.com/youtube/v3"

def requests_get_with_retry(url, params=None, max_retries=5, delay=5):
    for attempt in range(max_retries):
        try:
            return requests.get(url, params=params)
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                print(f"Network error: {e}. Retrying in {delay} seconds... (Attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
            else:
                raise e

def find_channel(channel_name):
    """Find a YouTube channel by name."""
    url = f"{BASE_URL}/search"
    params = {
        "part": "snippet",
        "q": channel_name,
        "type": "channel",
        "maxResults": 5,
        "key": API_KEY
    }
    response = requests_get_with_retry(url, params=params)
    if response.status_code != 200:
        print("Error finding channel:")
        print(response.text)
        return None
    data = response.json()
    if not data.get("items"):
        print("No channel found.")
        return None
    channel = None
    for item in data["items"]:
        if item["snippet"]["title"].lower() == channel_name.lower():
            channel = item
            break
    if not channel:
        print(f"Exact match for '{channel_name}' not found, falling back to the first result.")
        channel = data["items"][0]
    channel_id = channel["id"]["channelId"]
    channel_title = channel["snippet"]["title"]
    print("Selected channel")
    print("-" * 60)
    print("Name :", channel_title)
    print("Channel ID:", channel_id)
    return channel_id

def get_uploads_playlist(channel_id):
    """Get the upload playlist ID for a channel."""
    url = f"{BASE_URL}/channels"
    params = {
        "part": "contentDetails",
        "id": channel_id,
        "key": API_KEY
    }
    response = requests_get_with_retry(url, params=params)
    if response.status_code != 200:
        print("Error getting channel details:")
        print(response.text)
        return None
    data = response.json()
    if not data.get("items"):
        print("Channel details not found.")
        return None
    uploads_playlist_id = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print("\nUploads playlist")
    print("-" * 60)
    print("Playlist ID:", uploads_playlist_id)
    return uploads_playlist_id

def get_latest_long_video_id(playlist_id):
    """Get the latest uploaded long video (not a Short)."""
    url = f"{BASE_URL}/playlistItems"
    params = {
        "part": "snippet,contentDetails",
        "playlistId": playlist_id,
        "maxResults": 15,
        "key": API_KEY
    }
    response = requests_get_with_retry(url, params=params)
    if response.status_code != 200:
        print("Error getting videos:")
        print(response.text)
        return None
    data = response.json()
    items = data.get("items", [])
    if not items:
        return None
    video_ids = [item["contentDetails"]["videoId"] for item in items]
    videos_url = f"{BASE_URL}/videos"
    videos_params = {
        "part": "snippet,contentDetails",
        "id": ",".join(video_ids),
        "key": API_KEY
    }
    videos_response = requests_get_with_retry(videos_url, params=videos_params)
    if videos_response.status_code != 200:
        print("Error getting video details.")
        return None
    videos_data = videos_response.json()
    video_details = {v["id"]: v for v in videos_data.get("items", [])}
    for item in items:
        video_id = item["contentDetails"]["videoId"]
        details = video_details.get(video_id)
        if not details: continue
        duration = details["contentDetails"]["duration"]
        title = details["snippet"]["title"]
        # Accurately determine if a video is a Short by pinging the /shorts/ URL
        try:
            r = requests.head(f"https://www.youtube.com/shorts/{video_id}", allow_redirects=False, timeout=5)
            is_short = (r.status_code == 200)
        except Exception:
            # Fallback to simple duration check if network request fails
            is_short = ("M" not in duration) and ("H" not in duration)
        if not is_short and "#shorts" not in title.lower():
            published = details["snippet"]["publishedAt"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            print("\nLatest Long Video")
            print("=" * 60)
            print("Title :", title)
            print("Published :", published)
            print("Video ID :", video_id)
            print("Duration :", duration)
            print("URL :", video_url)
            print("-" * 60)
            return video_id
    print("No long videos found in recent uploads.")
    return None

def download_audio(video_id, output_path="audio.m4a"):
    print(f"Downloading audio for video {video_id} using yt-dlp...")
    import yt_dlp
    ydl_opts = {
        'format': 'worstaudio[ext=m4a]/worstaudio/bestaudio',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'retries': 10,
        'fragment_retries': 10,
        'extractor_args': {'youtube': ['player_client=ANDROID']}
    }
    if os.path.exists(output_path):
        os.remove(output_path)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
    return output_path

def run_groq_translation(audio_path):
    print("Uploading audio to Groq (Whisper Large v3) for translation...")
    api_key = os.environ.get("GROQ_API_KEY_Extraction") or os.environ.get("GROQ_API_KEY")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with open(audio_path, "rb") as f:
                headers = {
                    "Authorization": f"Bearer {api_key}"
                }
                files = {
                    "file": (os.path.basename(audio_path), f, "audio/m4a")
                }
                data = {
                    "model": "whisper-large-v3",
                    "response_format": "text"
                }
                response = requests.post("https://api.groq.com/openai/v1/audio/translations", headers=headers, files=files, data=data)
                
                if response.status_code != 200:
                    print(f"Groq API Error Response (Attempt {attempt+1}/{max_retries}):", response.text)
                    if response.status_code in [401, 403]:  # Don't retry auth errors
                        response.raise_for_status()
                    
                    if attempt < max_retries - 1:
                        time.sleep(10)
                        continue
                    response.raise_for_status()
                
                result = response.text.strip()
                print("Translation complete!")
                return result
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                print(f"Network error during translation: {e}. Retrying in 10 seconds... (Attempt {attempt+1}/{max_retries})")
                time.sleep(10)
            else:
                print(f"Translation failed after {max_retries} attempts due to network errors.")
                raise e
    
    return ""

def process_video(video_id):
    print(f"\n============================================================")
    print(f"Processing Video ID: {video_id}")
    print(f"============================================================")
    # Try fetching English transcript
    print("Checking for English transcript...")
    try:
        api = YouTubeTranscriptApi()
        # The user's original script uses api.fetch()
        fetched_data = api.fetch(video_id, languages=["en", "en-IN", "en-GB", "en-US", "ta"])
        # If it returned a transcript, let's see if it's English
        lang = getattr(fetched_data, 'language_code', 'unknown')
        if not lang.startswith('en'):
            # It's Tamil or something else, we want English
            raise ValueError("Not English")
        print("\nTranscript found!")
        print("Language:", getattr(fetched_data, 'language', lang))
        print("Language code:", lang)
        print("Auto-generated:", getattr(fetched_data, 'is_generated', False))
        # Create SRT
        formatter = SRTFormatter()
        # For this specific API version, fetch() returns an iterable of snippets
        srt_text = formatter.format_transcript(fetched_data)
        with open(os.path.join(SCRIPT_DIR, f"{video_id}.srt"), "w", encoding="utf-8") as file:
            file.write(srt_text)
        # Create plain text (handle if snippets are dicts or objects)
        try:
            plain_text = "\n".join(snippet['text'] for snippet in fetched_data)
        except TypeError:
            plain_text = "\n".join(snippet.text for snippet in fetched_data)
        with open(os.path.join(SCRIPT_DIR, f"{video_id}.txt"), "w", encoding="utf-8") as file:
            file.write(plain_text)
        print("\nFiles created successfully:")
        print(f"{video_id}.srt")
        print(f"{video_id}.txt")
        
        # NEW: Auto-trigger ingestion
        try:
            from ingest_bridge import ingest_video
            print("\nTriggering auto-ingestion pipeline...")
            ingest_video(video_id, f"http://localhost:{PORT}/ingest")
        except ImportError:
            print("\nCould not import ingest_bridge.py for auto-ingestion.")
        except Exception as err:
            print(f"\nFailed to auto-ingest {video_id}: {err}")
        return
    except Exception as e:
        print(f"No English transcript found: {e}")
        
    print("\nFalling back to Groq Audio translation...")
    audio_file = f"{video_id}_audio.m4a"
    download_audio(video_id, audio_file)
    plain_text = run_groq_translation(audio_file)
    if not plain_text.strip():
        print("WARNING: Groq returned empty translation!")
    if os.path.exists(audio_file):
        os.remove(audio_file)
    with open(os.path.join(SCRIPT_DIR, f"{video_id}.txt"), "w", encoding="utf-8") as file:
        file.write(plain_text)
    print(f"\nFile created successfully:")
    print(f"{video_id}.txt")
    
    # NEW: Auto-trigger ingestion
    try:
        from ingest_bridge import ingest_video
        print("\nTriggering auto-ingestion pipeline...")
        ingest_video(video_id, f"http://localhost:{PORT}/ingest")
    except ImportError:
        print("\nCould not import ingest_bridge.py for auto-ingestion.")
    except Exception as err:
        print(f"\nFailed to auto-ingest {video_id}: {err}")

def main():
    if API_KEY == "PASTE_YOUR_API_KEY_HERE":
        print("ERROR: Please add your YouTube API key.")
        return
    print("FeedToRead YouTube Pipeline")
    print("=" * 60)
    
    CHANNELS = fetch_active_channels()
    if not CHANNELS:
        print("No active YouTube channels found in backend.")
        return

    for channel_name in CHANNELS:
        print("\n" + "*" * 60)
        print(f"Processing channel: {channel_name}")
        print("*" * 60)
        channel_id = find_channel(channel_name)
        if not channel_id:
            continue
        playlist_id = get_uploads_playlist(channel_id)
        if not playlist_id:
            continue
        video_id = get_latest_long_video_id(playlist_id)
        if video_id:
            print(f"\nSuccessfully retrieved long video ID: {video_id} for {channel_name}")
            process_video(video_id)

if __name__ == "__main__":
    main()
