# twitter_publisher/agent.py — Publication sur Twitter via API v2
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
import json
import logging
import os

logging.basicConfig(
    format='%(asctime)s:%(levelname)s:%(message)s',
    encoding='utf-8'
)

TWITTER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "")


def post_tweet(text: str, media_ids: list = None) -> dict:
    """
    Publie un tweet simple sur Twitter.
    """
    if not TWITTER_TOKEN:
        return {"success": False, "message": "TWITTER_BEARER_TOKEN manquant"}
    
    url = "https://api.twitter.com/2/tweets"
    headers = {
        "Authorization": f"Bearer {TWITTER_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {"text": text}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            data = response.json()
            return {"success": True, "tweet_id": data.get("data", {}).get("id"), "message": "Tweet publié"}
        else:
            return {"success": False, "message": f"Erreur {response.status_code}: {response.text}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def post_thread(folder: str) -> dict:
    """
    Publie un thread Twitter depuis un dossier.
    """
    folder_path = Path(folder)
    tweet_files = sorted(folder_path.glob("tweet_*.txt"))
    
    if not tweet_files:
        return {"success": False, "message": "Aucun tweet dans le dossier"}
    
    last_tweet_id = None
    for i, tweet_file in enumerate(tweet_files):
        text = tweet_file.read_text(encoding="utf-8").strip()
        
        if i == 0:
            result = post_tweet(text)
        else:
            reply_param = {"reply": {"in_reply_to_tweet_id": last_tweet_id}} if last_tweet_id else {}
            result = post_tweet(text)
        
        if not result.get("success"):
            return {"success": False, "message": f"Erreur au tweet {i+1}: {result.get('message')}"}
        
        if i == 0:
            last_tweet_id = result.get("tweet_id")
        else:
            last_tweet_id = result.get("tweet_id")
    
    return {"success": True, "message": f"Thread de {len(tweet_files)} tweets publié"}


def post_twitter(identifier: str) -> dict:
    """
    Point d'entrée principal - publie soit un tweet soit un thread.
    """
    path = Path(identifier)
    
    if path.is_dir():
        if (path / "thread.json").exists():
            return post_thread(str(path))
        tweet_file = path / "tweet_1.txt"
        if tweet_file.exists():
            return post_tweet(tweet_file.read_text(encoding="utf-8").strip())
        return post_thread(str(path))
    
    tweet_file = Path(identifier)
    if tweet_file.exists() and tweet_file.suffix == ".txt":
        return post_tweet(tweet_file.read_text(encoding="utf-8").strip())
    
    return {"success": False, "message": "Fichier ou dossier introuvable"}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = post_twitter(sys.argv[1])
        print(result)
    else:
        print("Usage: python agent.py <folder_or_file>")