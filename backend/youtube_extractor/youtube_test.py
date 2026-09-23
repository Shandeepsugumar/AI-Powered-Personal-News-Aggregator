import requests
import sys

# Reconfigure stdout to support printing emojis and unicode characters on Windows
sys.stdout.reconfigure(encoding='utf-8')


API_KEY = "AIzaSyAKzmepENSN68GdOOncPmBBlzuKimtByTA"

# Channel name 
CHANNEL_NAME = "A2D Channel"

BASE_URL = "https://www.googleapis.com/youtube/v3"


def find_channel(channel_name):
    """Find a YouTube channel by name."""

    url = f"{BASE_URL}/search"

    params = {
        "part": "snippet",
        "q": channel_name,          # Use the function parameter
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

    # Find the exact match
    channel = None
    for item in data["items"]:
        if item["snippet"]["title"].lower() == channel_name.lower():
            channel = item
            break
            
    # Fallback to the first result if no exact match is found
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

    uploads_playlist_id = (
        data["items"][0]
        ["contentDetails"]
        ["relatedPlaylists"]
        ["uploads"]
    )

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
        "maxResults": 15, # Increased to ensure we find a long video even if there are many recent shorts
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

    # Get the video IDs to query their durations
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

    # Iterate over the originally ordered items (most recent first)
    for item in items:
        video_id = item["contentDetails"]["videoId"]
        details = video_details.get(video_id)
        if not details: continue
        
        duration = details["contentDetails"]["duration"]
        title = details["snippet"]["title"]
        
        # A video is a Short if its duration is under a minute (no 'M' or 'H' in ISO 8601 string)
        # e.g., 'PT59S' is a short, 'PT1M30S' is a long video.
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


def main():

    if API_KEY == "PASTE_YOUR_API_KEY_HERE":
        print("ERROR: Please add your YouTube API key.")
        return

    print("FeedToRead YouTube Test")
    print("=" * 60)

    print("\nSearching for channel:", CHANNEL_NAME)

    # Step 1: Find channel
    channel_id = find_channel(CHANNEL_NAME)

    if not channel_id:
        return

    # Step 2: Get uploads playlist
    playlist_id = get_uploads_playlist(channel_id)

    if not playlist_id:
        return

    # Step 3: Get latest long video
    video_id = get_latest_long_video_id(playlist_id)
    
    if video_id:
        print(f"\nSuccessfully retrieved long video ID: {video_id}")


if __name__ == "__main__":
    main()