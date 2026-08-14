# agent_publisher.py — Publication sur Twitter via API v2
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import config_manager
except Exception:
    import os
    class Config:
        TWITTER_TOKEN = os.getenv("TWITTER_TOKEN", "")
        TWITTER_USER_ID = os.getenv("TWITTER_USER_ID", "")
    config_manager = Config()

logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s:%(levelname)s:%(message)s',
    encoding='utf-8'
)

TWITTER_API = "https://api.twitter.com/2/tweets"


def get_twitter_credentials(account_id: int = None):
    """
    Récupère les credentials Twitter dynamiquement depuis la DB.
    Si account_id fourni, utilise les credentials de ce compte.
    Sinon, utilise le premier compte Twitter actif.
    Fallback sur le .env si DB incomplète.
    """
    try:
        sys.path.insert(0, "D:/Content_Machine/machines/facebook_machine")
        from core.db import SessionLocal, Account
        
        db = SessionLocal()
        try:
            if account_id:
                account = db.query(Account).filter(
                    Account.id == account_id,
                    Account.platform == "twitter",
                    Account.status == "active"
                ).first()
            else:
                account = db.query(Account).filter(
                    Account.platform == "twitter",
                    Account.status == "active"
                ).first()
            
            if account:
                creds = account.credentials or {}
                token = creds.get("access_token") or creds.get("token")
                
                if token:
                    print(f"✅ Utilisation compte Twitter DB ID={account.id} (name: {account.name})")
                    return token
            
            print("⚠️ Credentials DB incomplètes, fallback sur .env")
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️ Erreur DB, fallback sur .env: {e}")
    
    # Fallback: utiliser les variables d'environnement globales
    try:
        token = config_manager.TWITTER_TOKEN
        
        if token:
            print(f"✅ Utilisation compte Twitter depuis .env (global)")
            return token
    except Exception:
        pass
    
    print("❌ Aucun credentials Twitter disponible (DB + .env)")
    return None


def post_twitter(folder, account_id: int = None, credentials: dict = None):
    """Publie le contenu du dossier spécifié sur Twitter.
    
    Args:
        folder: chemin du dossier contenant tweet.txt
        account_id: ID du compte Twitter (optionnel)
        credentials: dict avec twitter_token et twitter_user_id (optionnel)
        
    Returns:
        True si publication réussie, False sinon
    """
    try:
        path = Path(folder)
        # Chercher tweet_post.txt ou tweet.txt
        tweet_file = path / "tweet_post.txt"
        if not tweet_file.exists():
            tweet_file = path / "tweet.txt"
        
        if not tweet_file.exists():
            print(f"❌ Erreur : tweet_post.txt ou tweet.txt introuvable dans {folder}")
            return False
        
        tweet_text = tweet_file.read_text(encoding="utf-8").strip()
        
        if len(tweet_text) > 280:
            print(f"⚠️ Tweet trop long ({len(tweet_text)} chars), troncature...")
            tweet_text = tweet_text[:277] + "..."
        
        # Utiliser les credentials fournis ou les récupérer depuis la DB
        if credentials:
            token = credentials.get("twitter_token") or credentials.get("access_token")
        else:
            token = get_twitter_credentials(account_id)
        
        if not token:
            print("❌ Erreur : Impossible de récupérer les credentials Twitter.")
            return False
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {"text": tweet_text}
        
        import requests
        response = requests.post(TWITTER_API, headers=headers, json=payload, timeout=30)
        
        if response.status_code in [200, 201]:
            result = response.json()
            tweet_id = result.get("data", {}).get("id", "")
            print(f"[SUCCESS] Tweet publié: {tweet_id}")
            return True
        else:
            error = f"Erreur Twitter {response.status_code}: {response.text}"
            logging.error(error)
            print(f"[ERROR] {error}")
            return False

    except Exception as e:
        logging.error(f"Erreur fatale : {e}")
        print(f"[ERROR] Erreur publication : {e}")
        return False


def post_tweet(folder):
    """Publie le contenu du dossier spécifié sur Twitter (legacy)."""
    result = post_twitter(folder, account_id=None)
    return {"success": result}


def post_thread(folder):
    """Publie un thread (plusieurs tweets)."""
    try:
        path = Path(folder)
        thread_file = path / "thread.json"
        
        if not thread_file.exists():
            print(f"⚠️ thread.json introuvable, essaye tweet.txt...")
            return post_twitter(folder, account_id=None)
            return post_tweet(folder)
        
        import requests
        
        thread_data = json.loads(thread_file.read_text(encoding="utf-8"))
        tweets = thread_data.get("tweets", [])
        
        if not tweets:
            return {"success": False, "message": "Aucun tweet dans le thread"}
        
        tweet_ids = []
        
        for i, tweet_text in enumerate(tweets):
            if len(tweet_text) > 280:
                tweet_text = tweet_text[:277] + "..."
            
            headers = {
                "Authorization": f"Bearer {config_manager.TWITTER_TOKEN}",
                "Content-Type": "application/json"
            }
            
            payload = {"text": tweet_text}
            response = requests.post(TWITTER_API, headers=headers, json=payload, timeout=30)
            
            if response.status_code not in [200, 201]:
                print(f"❌ Erreur tweet {i+1}: {response.status_code}")
                continue
            
            result = response.json()
            tweet_id = result.get("data", {}).get("id", "")
            tweet_ids.append(tweet_id)
            print(f"✅ Tweet {i+1}/{len(tweets)}: {tweet_id}")
        
        if tweet_ids:
            return {"success": True, "tweet_ids": tweet_ids, "count": len(tweet_ids)}
        return {"success": False, "message": "Aucun tweet publié"}

    except Exception as e:
        logging.error(f"Erreur thread : {e}")
        return {"success": False, "message": str(e)}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = post_tweet(sys.argv[1])
        print(result)
    else:
        print("Usage: python agent_publisher.py <folder_path>")