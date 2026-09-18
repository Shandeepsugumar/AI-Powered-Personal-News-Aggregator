import os
import json
import time
import sys
import requests
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

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

embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

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
            resp = requests.post(f"{OPENROUTER_URL}/chat/completions", headers=headers, json=payload, timeout=15)
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
            resp = requests.post(f"{GROQ_URL}/chat/completions", headers=headers, json=payload, timeout=10)
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
    """
    system_prompt = (
        "You are an AI news summarizer. You MUST output strict JSON only, with EXACTLY these keys:\n"
        '- "is_news": boolean (true if the content describes any real-world event, product, company action, rumor, leak, prediction, analyst report, or factual claim — even if short or speculative. Only set false for literal spam, filler text, or completely empty content)\n'
        '- "headline": string (crisp, engaging)\n'
        '- "summary": string (concise summary of the content)\n'
        '- "category": string (e.g. TECHNOLOGY, POLITICS, FINANCE)\n'
        '- "event": string (short description of the specific real-world event)\n'
        '- "key_facts": list of strings'
    )
    
    result_str = call_groq(MODEL_LLM1, system_prompt, raw_content)
    try:
        res = json.loads(result_str)
        if res.get("_status") == "failed":
            return {"_status": "failed"}
        return res
    except json.JSONDecodeError:
        return {"_status": "failed"}

def generate_embedding(text: str) -> List[float]:
    return embedding_model.encode(text).tolist()

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
