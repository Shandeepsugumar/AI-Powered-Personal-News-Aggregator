import os
import json
import time
import sys
import requests
from typing import List, Dict, Any
from fastembed import TextEmbedding
from dotenv import load_dotenv
from utils.content_parser import chunk_content

def safe_print(*args, **kwargs):
    """Print that won't crash on Windows cp1252 when LLM output has exotic Unicode."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(a) for a in args)
        print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"), **kwargs)

load_dotenv()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1"
GROQ_URL = "https://api.groq.com/openai/v1"

# The target models
MODEL_LLM1 = "openai/gpt-oss-120b"
MODEL_LLM2 = "deepseek/deepseek-v4-flash-0731:free"

embedding_model = TextEmbedding('BAAI/bge-small-en-v1.5')

def check_models_available():
    """Query OpenRouter to ensure our target free models are available."""
    if not OPENROUTER_API_KEY:
        print("WARNING: OPENROUTER_API_KEY not set. API calls will fail.")
        return
        
    try:
        resp = requests.get(f"{OPENROUTER_URL}/models")
        if resp.status_code == 200:
            data = resp.json()
            available_ids = [m['id'] for m in data.get('data', [])]
            if MODEL_LLM2 not in available_ids:
                print(f"WARNING: {MODEL_LLM2} is not currently in the OpenRouter models list.")
    except Exception as e:
        print(f"Failed to check OpenRouter models: {e}")

def call_openrouter(model: str, system_prompt: str, user_content: str, max_retries: int = 5) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }
    
    for attempt in range(max_retries):
        try:
            resp = requests.post(f"{OPENROUTER_URL}/chat/completions", headers=headers, json=payload, timeout=45)
        except Exception as e:
            print(f"OpenRouter Request Exception: {e}")
            wait_time = 2 ** attempt
            time.sleep(wait_time)
            continue
        
        if resp.status_code == 429:
            wait_time = 2 ** attempt
            print(f"Rate limited (429) on model {model}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
            continue
            
        if resp.status_code != 200:
            print(f"OpenRouter Error: {resp.text}")
            return "{}"
            
        try:
            content = resp.json()["choices"][0]["message"].get("content")
            return content if content is not None else "{}"
        except (KeyError, IndexError) as e:
            print(f"OpenRouter response format error: {resp.json()}")
            return "{}"
            
    print(f"Max retries reached for model {model}.")
    return "{}"

def call_groq(model: str, system_prompt: str, user_content: str, max_retries: int = 5) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }
    
    for attempt in range(max_retries):
        try:
            resp = requests.post(f"{GROQ_URL}/chat/completions", headers=headers, json=payload, timeout=60)
        except Exception as e:
            print(f"Groq Request Exception: {e}")
            wait_time = 2 ** attempt
            time.sleep(wait_time)
            continue
        
        if resp.status_code == 429:
            wait_time = 2 ** attempt
            print(f"Rate limited (429) on Groq model {model}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
            continue
            
        if resp.status_code != 200:
            print(f"Groq Error: {resp.text}")
            return '{"_status": "failed"}'
            
        try:
            content = resp.json()["choices"][0]["message"].get("content")
            return content if content is not None else '{"_status": "failed"}'
        except (KeyError, IndexError) as e:
            print(f"Groq response format error: {resp.json()}")
            return '{"_status": "failed"}'
            
    print(f"Max retries reached for Groq model {model}.")
    return '{"_status": "failed"}'


def summarize_content(raw_content: str) -> Dict[str, Any]:
    """
    LLM 1 (Content-level): Summarize raw content.
    Implements map-reduce chunking for long content (>15000 chars) to stay within context windows.
    """
    chunks = chunk_content(raw_content, max_chars=15000)
    
    # If content is short, do the standard single pass
    if len(chunks) == 1:
        return _summarize_single_pass(chunks[0])
        
    # Map Phase: extract key facts/summary per chunk
    print(f"Content length {len(raw_content)} exceeds threshold. Splitting into {len(chunks)} chunks.")
    chunk_summaries = []
    chunk_prompt = (
        "You are an AI assistant. Extract the main facts and a brief summary from this chunk of text. "
        "Output strict JSON with these keys:\n"
        '- "summary": string\n'
        '- "key_facts": list of strings\n'          '- "stance": "POSITIVE" | "NEUTRAL" | "NEGATIVE"'
    )
    
    for i, chunk in enumerate(chunks):
        print(f"  Processing chunk {i+1}/{len(chunks)}...")
        res_str = call_groq(MODEL_LLM1, chunk_prompt, chunk)
        try:
            chunk_data = json.loads(res_str)
            if chunk_data.get("_status") != "failed":
                chunk_summaries.append(f"Chunk {i+1}:\nSummary: {chunk_data.get('summary', '')}\nFacts: {', '.join(chunk_data.get('key_facts', []))}")
        except json.JSONDecodeError:
            print(f"  Warning: Failed to parse JSON for chunk {i+1}")
            
    if not chunk_summaries:
        return {"_status": "failed"}
        
    # Reduce Phase: combine partial summaries into final struct
    print("Combining chunk summaries into final output...")
    combined_text = "\n\n".join(chunk_summaries)
    return _summarize_single_pass(combined_text)

def _summarize_single_pass(content_text: str) -> Dict[str, Any]:
    system_prompt = (
        "You are an AI news summarizer. You MUST output strict JSON only, with EXACTLY these keys:\n"
        '- "is_news": boolean (true for VIRTUALLY EVERYTHING with actual substance worth summarizing — real news, analysis, comedy/entertainment performances, short films, vlogs, fiction, self-help/advice content, etc. ONLY set false for genuine spam, ads, empty/near-empty content, or pure boilerplate like "like and subscribe". If it is a video transcript of a film or story, it IS news/entertainment, set true)\n'
        '- "headline": string (crisp, engaging)\n'
        '- "summary": string (concise summary of the content)\n'
        '- "category": string (e.g. TECHNOLOGY, BUSINESS, POLITICS, SCIENCE, SPORTS, ENTERTAINMENT, OTHER. Note: "SCIENCE" includes psychology, neuroscience, cognitive science, and health/medical research. "TECHNOLOGY" is strictly for products, software, hardware, and engineering topics. Comedy/entertainment performances -> "ENTERTAINMENT". Self-help/motivational/personal-development -> "OTHER")\n'
        '- "event": string (short description of the specific event or subject)\n'
        '- "key_facts": list of strings\n'          '- "stance": "POSITIVE" | "NEUTRAL" | "NEGATIVE"'
    )
    
    result_str = call_groq(MODEL_LLM1, system_prompt, content_text)
    try:
        res = json.loads(result_str)
        if res.get("_status") == "failed":
            return {"_status": "failed"}
        return res
    except json.JSONDecodeError:
        return {"_status": "failed"}

def generate_embedding(text: str) -> List[float]:
    return next(embedding_model.embed([text])).tolist()

def merge_decision(new_item_summary: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    LLM 2 (Story-level): Receives a new item + Top-K candidates.
    Decides whether to merge, separate, or create new group.
    """
    system_prompt = (
        "You are an AI news editor. You are given a NEW ITEM and a list of CANDIDATES (existing active stories or other new items).\n"
        "Your task is to determine if the NEW ITEM covers the EXACT SAME real-world event as one of the CANDIDATES.\n"
        "Output strict JSON with these keys:\n"
        '- "reasoning": string (explain why you chose to merge, separate, or create new_group, and if facts agree or conflict)\n'
        '- "decision": "merge" | "new_group" | "separate"\n'
        '- "target_group_id": string (the ID of the matched candidate if merge/new_group, else null)\n'
        '- "has_conflict": boolean (true if facts disagree between sources, e.g. price, date, claim)\n'
        '- "final_headline": string\n'
        '- "final_summary": string\n'
        '- "category": string\n'
        '- "stance": "POSITIVE" | "NEUTRAL" | "NEGATIVE"\n\n'
        "CRITICAL RULES:\n"
        "- High similarity does NOT mean same event. 'iPhone 18 launch' vs 'iPhone 19 development' are DIFFERENT events. Choose 'separate'.\n"
        "- If the facts agree, choose 'merge' and combine the info.\n"
        "- If the facts DISAGREE (conflict), choose 'merge' (if same event) BUT YOU MUST EXPLICITLY ATTRIBUTE BOTH CLAIMS in the final_summary (e.g., 'Source A says X, while Source B says Y'). Never pick one silently.\n"
        "- If decision is 'new_group' or 'separate', final_headline and final_summary must be based SOLELY on the NEW item's own content — do not mention, reference, or merge in any information from the candidate story/stories it was compared against and rejected."
    )
    
    user_content = f"NEW ITEM:\n{json.dumps(new_item_summary, indent=2)}\n\nCANDIDATES:\n"
    for cand in candidates:
        user_content += f"- Candidate ID: {cand['id']}\n{json.dumps(cand, indent=2)}\n\n"
        
    result_str = call_openrouter(MODEL_LLM2, system_prompt, user_content)
    
    safe_print("\n================ LLM 2 RAW OUTPUT ================")
    safe_print(result_str)
    safe_print("==================================================\n")
    
    try:
        return json.loads(result_str)
    except json.JSONDecodeError:
        return {"decision": "separate", "target_group_id": None, "has_conflict": False, "final_headline": "Error", "final_summary": "Error", "category": "ERROR", "stance": "NEUTRAL", "reasoning": "Parse error"}
