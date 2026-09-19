import os
import requests
import warnings
import time
import sys
import re
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.formatters import SRTFormatter
import google.generativeai as genai

# Reconfigure stdout to support printing emojis and unicode characters on Windows
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings("ignore")

API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
CHANNELS = ["Almost Everything"]
BASE_URL = "https://www.googleapis.com/youtube/v3"

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

    response = requests.get(url, params=params)
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
    print("Name      :", channel_title)
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

    response = requests.get(url, params=params)
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

    response = requests.get(url, params=params)
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
    
    videos_response = requests.get(videos_url, params=videos_params)
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
            print("Title     :", title)
            print("Published :", published)
            print("Video ID  :", video_id)
            print("Duration  :", duration)
            print("URL       :", video_url)
            print("-" * 60)
            
            return video_id

    print("No long videos found in recent uploads.")
    return None

def download_audio(video_id, output_path="audio.m4a"):
    print(f"Downloading audio for video {video_id} using yt-dlp...")
    import yt_dlp
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': ['player_client=ANDROID']}
    }
    if os.path.exists(output_path):
        os.remove(output_path)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
    return output_path

def run_gemini_translation(audio_path):
    print("Uploading audio to Gemini for translation...")
    
    api_keys = [
        os.environ.get("GEMINI_API_KEY", ""),
        os.environ.get("GEMINI_API_KEY_2", "")
    ]
    api_keys = [k for k in api_keys if k]  # filter out empty keys
    
    from google import genai
    from google.genai import types
    prompt = "Listen to this audio. Transcribe and translate it into natural English. Return ONLY the final English translation text, with proper punctuation and formatting."
    result = ""
    
    # Configure safety settings to prevent false positive blocks
    config = types.GenerateContentConfig(
        safety_settings=[
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE)
        ]
    )
    
    for key_idx, current_key in enumerate(api_keys):
        print(f"Trying API Key {key_idx + 1}/{len(api_keys)}...")
        try:
            client = genai.Client(api_key=current_key)
            
            audio_file = client.files.upload(file=audio_path)
            
            print("Waiting for Google servers to process the audio file...")
            while audio_file.state.name == "PROCESSING":
                print(".", end="", flush=True)
                time.sleep(5)
                audio_file = client.files.get(name=audio_file.name)
                
            print()
            if audio_file.state.name == "FAILED":
                raise ValueError("Audio file processing failed on Gemini servers.")
                
            print("Prompting Gemini to translate the audio to English...")
            
            max_retries = 5
            success = False
            for attempt in range(max_retries):
                try:
                    response = client.models.generate_content(
                        model='gemini-3.8-flash',
                        contents=[prompt, audio_file],
                        config=config
                    )
                    result = response.text.strip() if response.text else ""
                    if not result and response.candidates and response.candidates[0].content.parts:
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, 'text') and part.text:
                                result += part.text
                            elif hasattr(part, 'audio_transcription') and hasattr(part.audio_transcription, 'text'):
                                result += part.audio_transcription.text
                        result = result.strip()
                    if not result:
                        print("DEBUG: Result is empty. Response Candidates:")
                        print(response.candidates)
                    print("Translation complete!")
                    success = True
                    break
                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        print(f"Rate limit exceeded on this API key: {e}")
                        break 
                        
                    if attempt < max_retries - 1:
                        print(f"Error during Gemini generation: {e}. Retrying in 20 seconds... (Attempt {attempt+1}/{max_retries})")
                        time.sleep(20)
                    else:
                        print(f"Gemini generation failed after {max_retries} retries: {e}")
                        
            try:
                client.files.delete(name=audio_file.name)
            except Exception as e:
                print(f"Failed to delete remote file: {e}")
                
            if success:
                return result
                
        except Exception as e:
            print(f"Error with API Key {key_idx + 1}: {e}")
            
    print("All API keys failed or exhausted.")
    return result

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
        
        with open(f"{video_id}.srt", "w", encoding="utf-8") as file:
            file.write(srt_text)
            
        # Create plain text (handle if snippets are dicts or objects)
        try:
            plain_text = "\n".join(snippet['text'] for snippet in fetched_data)
        except TypeError:
            plain_text = "\n".join(snippet.text for snippet in fetched_data)
        
        with open(f"{video_id}.txt", "w", encoding="utf-8") as file:
            file.write(plain_text)
            
        print("\nFiles created successfully:")
        print(f"{video_id}.srt")
        print(f"{video_id}.txt")
        return
        
    except Exception as e:
        print(f"No English transcript found: {e}")
        
    print("\nFalling back to Gemini Audio translation...")
    audio_file = f"{video_id}_audio.m4a"
    download_audio(video_id, audio_file)
    
    plain_text = run_gemini_translation(audio_file)
    
    if not plain_text.strip():
        print("WARNING: Gemini returned empty translation!")
        
    if os.path.exists(audio_file):
        os.remove(audio_file)
        
    with open(f"{video_id}.txt", "w", encoding="utf-8") as file:
        file.write(plain_text)
        
    print(f"\nFile created successfully:")
    print(f"{video_id}.txt")

def main():
    if API_KEY == "PASTE_YOUR_API_KEY_HERE":
        print("ERROR: Please add your YouTube API key.")
        return

    print("FeedToRead YouTube Pipeline")
    print("=" * 60)

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
