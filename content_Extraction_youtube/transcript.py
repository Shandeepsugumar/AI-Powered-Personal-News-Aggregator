import sys
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter

def main():
    if len(sys.argv) < 2:
        print("Usage: python transcript.py <video_id>")
        return
    VIDEO_ID = sys.argv[1]
    
    print("Fetching transcript...")
    print("Video ID:", VIDEO_ID)

    try:
        api = YouTubeTranscriptApi()

        transcript = api.fetch(
            VIDEO_ID,
            languages=["ta", "en"]
        )

        print("\nTranscript found!")
        print("Language:", transcript.language)
        print("Language code:", transcript.language_code)
        print("Auto-generated:", transcript.is_generated)

        # Create SRT
        formatter = SRTFormatter()
        srt_text = formatter.format_transcript(transcript)

        with open(
            f"{VIDEO_ID}.srt",
            "w",
            encoding="utf-8"
        ) as file:
            file.write(srt_text)

        # Create plain text
        plain_text = "\n".join(
            snippet.text
            for snippet in transcript
        )

        with open(
            f"{VIDEO_ID}.txt",
            "w",
            encoding="utf-8"
        ) as file:
            file.write(plain_text)

        print("\nFiles created successfully:")
        print(f"{VIDEO_ID}.srt")
        print(f"{VIDEO_ID}.txt")

    except Exception as e:
        print("\nTranscript fetch failed.")
        print("Error:", type(e).__name__)
        print("Message:", e)


if __name__ == "__main__":
    main()