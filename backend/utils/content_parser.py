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

def chunk_content(text: str, max_chars: int = 15000, overlap: int = 500) -> list[str]:
    """
    Splits text into chunks of max_chars with overlap.
    Prefers splitting on paragraph or sentence boundaries.
    """
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = min(start + max_chars, text_len)
        
        if end == text_len:
            chunks.append(text[start:end].strip())
            break
            
        # Try to find a good split point
        split_pos = text.rfind('\n\n', start, end)
        if split_pos <= start + (max_chars // 2):
            split_pos = text.rfind('. ', start, end)
            if split_pos != -1:
                split_pos += 2 # include period and space
                
        if split_pos <= start + (max_chars // 2):
            split_pos = end # hard split
            
        chunks.append(text[start:split_pos].strip())
        
        # Advance start, ensuring we move forward
        new_start = split_pos - overlap
        if new_start <= start:
            new_start = split_pos # force progress if overlap is too big
        start = new_start
        
    return chunks
