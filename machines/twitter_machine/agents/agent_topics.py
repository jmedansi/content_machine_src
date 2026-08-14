# agent_topics.py — Utilitaires Twitter
import sys
import io
import requests
import json
import logging
import random
from pathlib import Path

try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except:
    pass

logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

# Try to import from config_manager
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agents import config_manager
except Exception:
    import os
    class Config:
        GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    config_manager = Config()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def groq_request(prompt, system=None, max_tokens=500):
    """Effectue une requête à l'API Groq."""
    if not config_manager.GROQ_API_KEY:
        raise Exception("GROQ_API_KEY manquante")
    
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    response = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {config_manager.GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        },
        timeout=60
    )
    
    if response.status_code != 200:
        raise Exception(f"Groq error {response.status_code}: {response.text}")
    
    result = response.json()
    return result["choices"][0]["message"]["content"]


def generate_topics(n=5, account_id=1):
    """Génère des sujets pour Twitter en utilisant l'agent partagé."""
    try:
        sys.path.insert(0, "D:/Content_Machine")
        from shared_agents.topic_finder.agent import suggest_persona_topics, get_active_personas
        
        personas = get_active_personas(account_id, platform="twitter")
        if not personas:
            personas = ["expert_ia"] # fallback standard
            
        all_topics = []
        for p in personas:
            res = suggest_persona_topics(p, count=max(1, n // len(personas)), account_id=account_id, platform="twitter")
            if res.success:
                topics_list = res.data.get("topics", [])
                for t in topics_list:
                    all_topics.append({
                        "title": t.get("topic") or t.get("title") or "",
                        "angle": t.get("context") or t.get("angle") or "",
                        "persona": p,
                        "validated": False,
                        "variables": t.get("variables", {})
                    })
        
        # Sauvegarder dans topics_pending.json (legacy)
        data_dir = Path("accounts") / str(account_id) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        pending_path = data_dir / "topics_pending.json"
        pending_path.write_text(json.dumps({"topics": all_topics}, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # Sauvegarder dans planned_topics.json (nouveau format)
        planned_path = Path("accounts") / str(account_id) / "planned_topics.json"

        planned_topics = []
        if planned_path.exists():
            try:
                planned_data = json.loads(planned_path.read_text(encoding="utf-8"))
                if "version" in planned_data and "topics" in planned_data:
                    planned_topics = planned_data["topics"]
            except:
                pass

        for t in all_topics:
            planned_topics.append({
                "id": str(random.randint(100000, 999999)),
                "persona": t["persona"],
                "topic": t["title"],
                "context": t["angle"],
                "media": "none",
                "date": "",
                "time": "",
                "validated": False,
                "used": False,
            })

        save_data = {"version": "1.0", "topics": planned_topics}
        planned_path.parent.mkdir(parents=True, exist_ok=True)
        planned_path.write_text(json.dumps(save_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        print(f"✅ {len(all_topics)} sujets générés")
        return all_topics
    except Exception as e:
        logging.error(f"Erreur generate_topics : {e}")
        return []


if __name__ == "__main__":
    generate_topics(5)