# agent_writer.py — Rédaction des posts Twitter via Groq
import sys
import io
import json
import re
import logging
from pathlib import Path
from datetime import datetime

# Try to import agent_topics utilities
try:
    from agents.agent_topics import groq_request
except ImportError:
    groq_request = None

# Try to import google_sheets utilities
try:
    from agents.google_sheets_utils import log_to_sheet
except ImportError:
    log_to_sheet = None

# Try to import persona_loader dynamic (nouveau mode)
try:
    from agents.persona_loader import load_personas, get_persona
    DYNAMIC_MODE = True
except ImportError:
    DYNAMIC_MODE = False
    load_personas = lambda: []
    get_persona = lambda x: None

# Try to import config_manager
try:
    from agents import config_manager
except Exception:
    import os
    class Config:
        GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    config_manager = Config()

SYSTEM_BASE = """Tu rédiges des tweets pour un expert digital francophone.

Son profil :
- Fondateur solo d'IncidenX, agence web et IA
- Ancien rédacteur web SEO, maîtrise le digital dans son ensemble
- Crée des agents IA, automatisations, sites web, applications
- Cible : dirigeants de PME en Europe et Afrique

Règles de format Twitter strictes :
- Maximum 280 caractères par tweet
- Pour les threads : chaque tweet max 280 caractères, thread cohérent
- Pas de bullet points — texte fluide
- Accroche forte en premier tweet
- Hashtags en fin (max 2-3)
- Pas de thread par défaut — sauf demande explicite

Ton : direct, percutant, expert qui共享."""


PROMPTS = {
    "hot_take": """FORMAT : Hot Take (opinion forte)

Un tweet unique, percutant.
Début corrosif ou constat tranchant.
Fin avec hashtags minimalistes.""",

    "thread": """FORMAT : Thread (fil de tweets)

3-5 tweets maximum.
Chaque tweet max 280 caractères.
Structure :
1. Accroche (le problème)
2. Développement (2-3 tweets)
3. Conclusion (CTA ou résumé)

Utilise des numéros pour lier les tweets.""",

    "meme": """FORMAT : Meme / blague tech

Court, humoristique, relatable pour les geeks/ devs.
Émoji OK.
Max 280 caractères."""
}


# Legacy - kept for fallback
PERSONAS = {
    "hot_take": {
        "name": "Hot Take",
        "system_prompt": PROMPTS["hot_take"],
        "max_words": 50,
        "max_chars": 280,
    },
    "thread_maker": {
        "name": "Thread",
        "system_prompt": PROMPTS["thread"],
        "max_words": 200,
        "max_chars": 1400,
    },
    "meme_lord": {
        "name": "Meme",
        "system_prompt": PROMPTS["meme"],
        "max_words": 40,
        "max_chars": 280,
    },
}


def load_personas():
    """Charge les personas depuis le dossier persona/."""
    personas_dir = Path("persona")
    if not personas_dir.exists():
        return PERSONAS
    
    personas = {}
    for folder in personas_dir.iterdir():
        if not folder.is_dir():
            continue
        if folder.name.startswith('_'):
            continue
        
        config_file = folder / "config.json"
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text(encoding="utf-8"))
                personas[folder.name] = config
            except Exception:
                pass
    
    return personas if personas else PERSONAS


def slugify(text: str) -> str:
    """Convertit un texte en slug URL-safe."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


def generate_tweet(topic: dict, persona_name: str = "hot_take", account_id: int = None, indication: str = None) -> tuple[str, str, str]:
    """Génère un tweet pour un sujet donné - MODE 100% DYNAMIQUE.
    
    Args:
        topic: Dict avec titre, angle
        persona_name: Nom du persona
        account_id: Si fourni, charge le persona depuis acc_{account_id}/persona/
        indication: Instruction optionnelle pour guider la régénération
    
    Returns:
        (tweet_text, persona_name, image_prompt)
    """
    # OBLIGATOIRE: charger depuis les personas dynamiques (par compte si account_id)
    persona = get_persona(persona_name, account_id=account_id)
    if not persona:
        # Erreur si persona non trouvé - pas de fallback
        raise ValueError(f"Persona '{persona_name}' introuvable dans persona/ du compte {account_id if account_id else 'global'}")
    
    max_chars = persona["config"].get("max_chars", 280)
    system = persona.get("system_prompt", "")
    
    titre = topic.get("titre", topic.get("title", ""))
    angle = topic.get("angle", "")
    
    prompt = f"""Sujet : {titre}
Angle : {angle}

Tu dois OBLIGATOIREMENT répondre au format JSON.
Ton JSON doit contenir exactement ces deux clés :
1. "post_content": Le texte complet du tweet ({max_chars} caractères max), respectant le style et le ton demandés.
2. "image_prompt": Un prompt en anglais pour illustrer ce tweet (pas de texte visible, scène vivante, style photographique précis).

Réponds UNIQUEMENT avec le code JSON, sans aucun texte avant ou après."""
    
    if indication:
        prompt += f"\n\nINSTRUCTION SPÉCIALE POUR CETTE RÉGÉNÉRATION :\n{indication}\nPrends cette remarque en compte IMPÉRATIVEMENT."

    try:
        result = groq_request(prompt, system=system)
        if not result:
            return f"Erreur: pas de réponse", persona_name, ""
        
        # Parsing JSON
        clean_json = result.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json.split("```json", 1)[1]
        if clean_json.endswith("```"):
            clean_json = clean_json.rsplit("```", 1)[0]
        clean_json = clean_json.strip()
        
        try:
            parsed = json.loads(clean_json)
            tweet_text = parsed.get("post_content", result)
            image_prompt = parsed.get("image_prompt", "")
        except json.JSONDecodeError:
            logging.error("[TWITTER] L'IA n'a pas respecté le format JSON. Fallback sur raw.")
            tweet_text = result
            image_prompt = ""
        
        return tweet_text, persona_name, image_prompt
    except Exception as e:
        logging.error(f"Erreur generation tweet : {e}")
        return f"Erreur: {e}", persona_name, ""


def write_validated_topics(account_id: int = None):
    """Rédige les sujets validés dans topics_pending.json.
    
    Args:
        account_id: Si fourni, enregistre dans accounts/<id>/content/
    """
    # Chercher les topics
    if account_id:
        topics_path = Path("accounts") / str(account_id) / "data" / "topics_pending.json"
        if not topics_path.exists():
            topics_path = Path("data") / "topics_pending.json"
    else:
        topics_path = Path("data/topics_pending.json")
    
    if not topics_path.exists():
        print(f"⚠️ topics_pending.json introuvable ({topics_path}).")
        return []
    
    try:
        data = json.loads(topics_path.read_text(encoding="utf-8"))
        topics = data.get("topics", [])
    except Exception as e:
        logging.error(f"Erreur lecture topics : {e}")
        return []
    
    validated = [t for t in topics if t.get("validated") is True]
    if not validated:
        print("ℹ️ Aucun sujet validé.")
        return []

    print(f"✍️ Rédaction de {len(validated)} tweet(s)...")
    
    folders = []
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    
    for topic in validated:
        titre = topic.get("titre", topic.get("title", ""))
        slug = slugify(titre)[:50]
        folder_name = f"{date_str}_{slug}"
        
        # Enregistrement dans le bon dossier (par compte ou global)
        if account_id:
            content_dir = Path("accounts") / str(account_id) / "content"
        else:
            content_dir = Path("content")
        
        folder = content_dir / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        
        persona_name = topic.get("persona", "hot_take")
        tweet_text, _, image_prompt = generate_tweet(topic, persona_name, account_id=account_id)
        
        post_file = folder / "tweet.txt"
        post_file.write_text(tweet_text, encoding="utf-8")
        
        meta = {
            "titre": titre,
            "topic": topic,
            "persona": persona_name,
            "created": now.isoformat(),
            "published": False,
            "status": "pending",
            "account_id": account_id,
        }
        if image_prompt:
            meta["image_prompt"] = image_prompt
        meta_file = folder / "meta.json"
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        
        folders.append(folder)
        print(f"✅ {folder_name}")

    return folders


def regenerate_post(folder_path: str, new_topic: dict = None, account_id: int = None, indication: str = None):
    """Régénère un post existant DANS LE MÊMe DOSSIER.
    
    Args:
        folder_path: Chemin du dossier
        new_topic: Nouveau topic (optionnel)
        account_id: ID du compte (pour charger les personas du bon compte)
        indication: Note optionnelle pour guider la régénération
    """
    folder = Path(folder_path)
    if not folder.exists():
        print(f"⚠️ Dossier introuvable: {folder_path}")
        return False
    
    meta_file = folder / "meta.json"
    if not meta_file.exists():
        print("⚠️ meta.json introuvable")
        return False
    
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        topic = new_topic or meta.get("topic", {})
        persona_name = meta.get("persona", "hot_take")
        existing_image_prompt = meta.get("image_prompt", "")
        
        tweet_text, _, new_image_prompt = generate_tweet(topic, persona_name, account_id=account_id, indication=indication)
        
        post_file = folder / "tweet.txt"
        post_file.write_text(tweet_text, encoding="utf-8")
        
        # Préservation de l'image_prompt existant si le LLM n'en génère pas un nouveau
        if new_image_prompt:
            meta["image_prompt"] = new_image_prompt
        elif existing_image_prompt:
            meta["image_prompt"] = existing_image_prompt  # préservation
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        
        print(f"✅ Post régénéré dans {folder.name}")
        return True
    except Exception as e:
        logging.error(f"Erreur regenerate_post : {e}")
        return False


if __name__ == "__main__":
    write_validated_topics()