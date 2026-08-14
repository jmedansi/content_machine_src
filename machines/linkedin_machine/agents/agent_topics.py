# agent_topics.py — Génération de sujets via Groq
import sys
import io
import requests
import json
import os
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path
import config_manager
from agents.google_sheets_utils import log_to_sheet

# Forcer l'encodage UTF-8 pour le terminal Windows (si possible)
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except (AttributeError, io.UnsupportedOperation):
    pass

# Configuration du logging
logging.basicConfig(
    filename='errors.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_TOPICS = """Tu es un expert en stratégie de contenu LinkedIn pour IncidenX, agence web et IA.
Tu génères un planning hebdomadaire de 7 posts (un par jour).

Ton profil :
- Fondateur d'une agence web et IA.
- Expertise : agents IA, automatisations, SEO, création de sites.
- Ton : Humain, direct, expert, pas de jargon technique.

Règles :
- Réponds UNIQUEMENT en JSON.
- Pas de chiffres inventés, pas de faux résultats clients.
- Chaque jour doit être unique et utile."""

def groq_request(prompt, system=SYSTEM_TOPICS, max_tokens=1500, temperature=0.5):
    """Effectue une requête à l'API Groq."""
    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {config_manager.GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": config_manager.GROQ_MODEL,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt}
                ]
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logging.error(f"Erreur requête Groq (topics) : {e}")
        return None

def load_memory():
    p = Path("data/memory.json")
    if not p.exists(): return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [item["titre"].lower() for item in data]
    except Exception: return []

def get_week_schedule():
    today = datetime.now()
    days_ahead = 0 - today.weekday()
    if days_ahead <= 0: days_ahead += 7
    next_monday = today + timedelta(days=days_ahead)
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    return {jours[i]: (next_monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}

def generate_topics(n=5, account_id=1):
    """Génère des sujets pour LinkedIn en utilisant l'agent partagé."""
    try:
        sys.path.insert(0, "D:/Content_Machine")
        from shared_agents.topic_finder.agent import suggest_persona_topics, get_active_personas
        
        personas = get_active_personas(account_id, platform="linkedin")
        if not personas:
            personas = ["b2b_expert"] # fallback standard
            
        all_topics = []
        for p in personas:
            res = suggest_persona_topics(p, count=max(1, n // len(personas)), account_id=account_id, platform="linkedin")
            if res.success:
                topics_list = res.data.get("topics", [])
                for t in topics_list:
                    # Adapter au format attendu par la legacy LinkedIn Machine
                    all_topics.append({
                        "jour": "Lundi", # valeur fictive
                        "format_id": t.get("format_id") or "post",
                        "format_nom": p,
                        "titre": t.get("topic") or t.get("title") or "",
                        "angle": t.get("context") or t.get("angle") or "",
                        "promesse": t.get("context") or "",
                        "secteur": "IA & Web",
                        "probleme": "",
                        "score_pertinence": 10,
                        "validated": False,
                        "date_generee": datetime.now().isoformat(),
                        "variables": t.get("variables", {})
                    })
        
        # Sauvegarder dans topics_pending.json (legacy)
        data_dir = Path("accounts") / str(account_id) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        pending_path = data_dir / "topics_pending.json"
        pending_path.write_text(json.dumps(all_topics, ensure_ascii=False, indent=2), encoding="utf-8")
        
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
                "persona": t["format_nom"],
                "topic": t["titre"],
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
        
        print(f"✅ {len(all_topics)} sujets générés.")
        return all_topics
    except Exception as e:
        logging.error(f"Erreur generate_topics : {e}")
        raise e

def add_manual_topic(topic_data):
    """Ajoute ou remplace un sujet manuellement pour un jour précis dans topics_pending.json."""
    try:
        pending_path = Path("data/topics_pending.json")
        topics = []
        if pending_path.exists():
            topics = json.loads(pending_path.read_text(encoding="utf-8"))
        
        jour_cible = topic_data.get("jour")
        
        # Récupérer la date prévue pour ce jour
        schedule = get_week_schedule()
        date_prevue = schedule.get(jour_cible)
        
        # Supprime l'ancien sujet prévu pour ce jour s'il existe
        topics = [t for t in topics if t.get("jour") != jour_cible]
        
        # Prépare le nouveau sujet
        new_topic = {
            "jour": jour_cible,
            "format_id": topic_data.get("format_id", "conseil"),
            "format_nom": topic_data.get("format_nom", "Sujet Manuel"),
            "titre": topic_data.get("titre", "Titre manuel"),
            "angle": topic_data.get("angle", ""),
            "promesse": topic_data.get("promesse", ""),
            "secteur": topic_data.get("secteur", "Général"),
            "probleme": topic_data.get("probleme", ""),
            "score_pertinence": 10,
            "date_prevue": date_prevue,
            "validated": True,
            "date_generee": datetime.now().isoformat(),
            "is_manual": True
        }
        
        topics.append(new_topic)
        
        # Tri et sauvegarde
        topics.sort(key=lambda x: x.get("date_prevue", ""))
        pending_path.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # Log Sheets
        log_to_sheet("Topics_Pending", [datetime.now().strftime("%Y-%m-%d"), new_topic["titre"], new_topic["secteur"], "MANUEL"])
        
        print(f"✅ Sujet manuel ajouté pour {jour_cible}.")
        return new_topic
    except Exception as e:
        logging.error(f"Erreur add_manual_topic : {e}")
        raise e

if __name__ == "__main__":
    generate_topics()
