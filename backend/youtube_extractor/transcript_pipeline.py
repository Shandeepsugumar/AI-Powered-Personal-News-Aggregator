import os
PORT = os.environ.get("PORT", "8000")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
import requests
import warnings
import time
import json
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import re
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# Suppress some warnings
warnings.filterwarnings("ignore")

OLLAMA_URL = "http://127.0.0.1:11435/api/generate"
OLLAMA_MODEL = "qwen3.5:9b"

def fetch_video_metadata(video_id):
    """
    Fetch video title, channel name, and upload date using yt-dlp (no download).
    Returns a dict ready to be written as the sidecar JSON.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        import yt_dlp
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        # upload_date is YYYYMMDD string; convert to ISO 8601
        raw_date = info.get("upload_date", "")
        if raw_date and len(raw_date) == 8:
            published_at = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}T00:00:00Z"
        else:
            published_at = None
        return {
            "video_id": video_id,
            "title": info.get("title", ""),
            "channel_name": info.get("uploader") or info.get("channel", ""),
            "published_at": published_at,
            "url": url,
        }
    except Exception as e:
        print(f"Warning: Could not fetch video metadata for {video_id}: {e}")
        return {
            "video_id": video_id,
            "title": "",
            "channel_name": "",
            "published_at": None,
            "url": url,
        }


def translate_text_with_ollama(tamil_text):
    print("Translating Tamil text to English using local Ollama...")
    prompt = f"Translate the following Tamil transcript into natural English. Return only the English translation.\n\n{tamil_text}"
    try:
        response = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=600)
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
        print(f"Error communicating with Ollama: {e}")
        return tamil_text

def fetch_from_api(video_id):
    try:
        api = YouTubeTranscriptApi()
        # Fetch English directly
        try:
            fetched_data = api.fetch(video_id, languages=['en', 'en-IN', 'en-GB', 'en-US'])
            class DummyTranscript:
                def fetch(self): return fetched_data
            return DummyTranscript(), 'en'
        except Exception:
            pass
            
        # Fallback to Tamil
        try:
            fetched_data = api.fetch(video_id, languages=['ta'])
            class DummyTranscript:
                def fetch(self): return fetched_data
            return DummyTranscript(), 'ta'
        except Exception:
            pass
            
        return None, None
    except Exception as e:
        print(f"YouTube API failed to find transcript: {type(e).__name__} - {e}")
        return None, None

def download_audio(video_id, output_path="audio.m4a"):
    print(f"Downloading audio for video {video_id} using yt-dlp...")
    import yt_dlp
    ydl_opts = {'format': 'm4a/bestaudio/best', 'outtmpl': output_path, 'quiet': True, 'no_warnings': True}
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
    prompt = "Listen to this audio. Transcribe and translate it into natural English. Return ONLY the final English translation text, with proper punctuation and formatting."
    result = ""
    
    for key_idx, current_key in enumerate(api_keys):
        print(f"Trying API Key {key_idx + 1}/{len(api_keys)}...")
        try:
            client = genai.Client(api_key=current_key)
            
            # Upload the file
            audio_file = client.files.upload(file=audio_path)
            
            # Wait for the file to be processed
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
                        contents=[prompt, audio_file]
                    )
                    # Safely get text, fallback to empty string if None
                    result = response.text.strip() if response.text else ""
                    if not result and response.candidates and response.candidates[0].content.parts:
                        # If text is None, try to extract from parts directly (for specialized models)
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, 'text') and part.text:
                                result += part.text
                            elif hasattr(part, 'audio_transcription') and hasattr(part.audio_transcription, 'text'):
                                result += part.audio_transcription.text
                        result = result.strip()
                    print("Translation complete!")
                    success = True
                    break
                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        print(f"Rate limit exceeded on this API key: {e}")
                        break # Break inner retry loop to move to the next API key
                        
                    if attempt < max_retries - 1:
                        print(f"Error during Gemini generation: {e}. Retrying in 20 seconds... (Attempt {attempt+1}/{max_retries})")
                        time.sleep(20)
                    else:
                        print(f"Gemini generation failed after {max_retries} retries: {e}")
                        
            # Delete the file from Gemini servers to save quota
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
    print(f"============================================================")
    print(f"Processing Video ID: {video_id}")
    print(f"============================================================")
    
    # Try API
    transcript_obj, lang = fetch_from_api(video_id)
    plain_text = ""
    
    if transcript_obj and lang == 'en':
        print("SUCCESS: Found English transcript directly via YouTube API!")
        fetched_data = transcript_obj.fetch()
        plain_text = "\n".join(getattr(snippet, 'text', '') for snippet in fetched_data)
        
    elif transcript_obj and lang == 'ta':
        print("SUCCESS: Found Tamil transcript via YouTube API!")
        fetched_data = transcript_obj.fetch()
        tamil_plain = "\n".join(getattr(snippet, 'text', '') for snippet in fetched_data)
        plain_text = translate_text_with_ollama(tamil_plain)
        
    else:
        print("NO TRANSCRIPT FOUND. Falling back to Gemini Audio translation...")
        audio_file = f"{video_id}_audio.m4a"
        download_audio(video_id, audio_file)
        
        plain_text = run_gemini_translation(audio_file)
        
        if os.path.exists(audio_file):
            os.remove(audio_file)
            
    # Save Output
    with open(os.path.join(SCRIPT_DIR, f"{video_id}.txt"), "w", encoding="utf-8") as f:
        f.write(plain_text)
        
    print(f"\nFile created successfully:")
    print(f"{video_id}.txt")
    
    # Save metadata sidecar JSON
    meta = fetch_video_metadata(video_id)
    meta_path = os.path.join(SCRIPT_DIR, f"{video_id}.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"{video_id}.json  (title: {meta.get('title', 'unknown')}, channel: {meta.get('channel_name', 'unknown')})")
    
    # NEW: Auto-trigger ingestion
    try:
        from ingest_bridge import ingest_video
        print("\nTriggering auto-ingestion pipeline...")
        ingest_video(video_id, f"http://localhost:{PORT}/ingest")
    except ImportError:
        print("\nCould not import ingest_bridge.py for auto-ingestion.")
    except Exception as err:
        print(f"\nError during auto-ingestion: {err}")

def extract_video_id(url_or_id):
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:\?|&|$)', url_or_id)
    if match:
        return match.group(1)
    return url_or_id

if __name__ == "__main__":
    import sys
    input_str = sys.argv[1] if len(sys.argv) > 1 else "RwzC-nTafDk"
    vid = extract_video_id(input_str)
    process_video(vid)
