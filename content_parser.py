import hashlib
import re

def parse_content(raw_content: str) -> str:
    """
    Performs light cleanup on the already-extracted upstream text.
    - Strips transcript artifacts like speaker markers (">>").
    - Removes excessive filler or repeated whitespace/newlines.
    """
    if not raw_content:
        return ""
        
    # Remove >> speaker markers common in transcripts
    cleaned = re.sub(r">>\s*", "", raw_content)
    
    # Normalize multiple newlines/spaces
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    
    return cleaned.strip()

def compute_content_hash(text: str) -> str:
    """
    Generates SHA-256 hash of raw content for exact-duplicate detection.
    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def is_meaningful_content(text: str) -> bool:
    """
    Check if content is long enough to be meaningful.
    If it's too short (e.g., < 20 chars), mark invalid and skip LLM.
    """
    return len(text.strip()) >= 20
