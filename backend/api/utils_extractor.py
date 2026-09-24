import subprocess
import sys
import os
from pathlib import Path

def trigger_extractors():
    backend_dir = Path(__file__).parent.parent.resolve()
    
    # Path to youtube_extractor
    yt_script = backend_dir / "youtube_extractor" / "main.py"
    # Path to rss_extractor
    rss_script = backend_dir / "rss_extractor" / "main.py"
    
    env = dict(os.environ, PYTHONPATH=str(backend_dir))
    cwd = str(backend_dir) # Run directly from backend dir
    
    try:
        subprocess.Popen([sys.executable, str(yt_script)], cwd=cwd, env=env)
        print("[Auto-Trigger] Spawned youtube_extractor/main.py in background")
    except Exception as e:
        print(f"[Auto-Trigger] Failed to start youtube_extractor: {e}")
        
    try:
        subprocess.Popen([sys.executable, str(rss_script)], cwd=cwd, env=env)
        print("[Auto-Trigger] Spawned rss_extractor/main.py in background")
    except Exception as e:
        print(f"[Auto-Trigger] Failed to start rss_extractor: {e}")
