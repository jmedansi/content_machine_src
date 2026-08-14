# agent_writer.py — Rédaction des posts LinkedIn via Groq
import sys
import io
import json
import re
import logging
from pathlib import Path
from datetime import datetime
import config_manager
from agents.agent_topics import groq_request
from agents.google_sheets_utils import log_to_sheet

# Import dynamique OBLIGATOIRE des personas
from agents.persona_loader import load_personas, get_persona

# Forcer l encodage UTF-8 pour le terminal Windows (si possible)
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except (AttributeError, io.UnsupportedOperation):
    pass

# Configuration du logging
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

def slugify(titre):
    """Transforme un titre en slug."""
    slug = titre.lower()
    for src, dst in [('àâä','a'),('éèêë','e'),('îï','i'),('ôö','o'),('ùûü','u'),('ç','c')]:
        for c in src:
            slug = slug.replace(c, dst)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug.strip())
    return slug[:60]

def write_linkedin_post(topic, indication=None, account_id: int = None, folder_path: str = None):
    """Rédige un post LinkedIn suivant son format spécifique - MODE 100% DYNAMIQUE.
    
    Args:
        topic: Dict avec titre, angle, format_id, etc.
        indication: Remarque optionnelle de l'utilisateur pour la rédaction
        account_id: ID du compte. Si fourni, charge personas depuis accounts/<id>/persona/
               et enregistre dans accounts/<id>/content/
        folder_path: Chemin optionnel du dossier cible. Si fourni, écrit dedans
               au lieu de créer un nouveau dossier.
    """
    format_id = topic.get("format_id", "conseil")
    
    # OBLIGATOIRE: charger depuis les personas dynamiques (par compte si account_id)
    persona = get_persona(format_id, account_id=account_id)
    if not persona:
        # Erreur si persona non trouvé - pas de fallback
        raise ValueError(f"Persona '{format_id}' introuvable dans persona/ du compte {account_id if account_id else 'global'}")
    
    system = persona["system_prompt"]
    config = persona["config"]
    min_words = config.get("min_words", 150)
    max_words = config.get("max_words", 220)
    
    format_data = persona.get("format")
    variables = topic.get("variables", {})

    if format_data and format_data.get("user_prompt_template") and variables:
        user_prompt = format_data["user_prompt_template"]
        for k, v in variables.items():
            user_prompt = user_prompt.replace(f"{{{k}}}", str(v))
        
        prompt = f"""{user_prompt}

EXEMPLES DE POSTS À IMITER (structure, ton, longueur) :
{persona.get('examples', '')}

Tu dois OBLIGATOIREMENT répondre au format JSON.
Ton JSON doit contenir exactement ces deux clés :
1. "post_content": Le texte complet du post LinkedIn ({min_words}-{max_words} mots), respectant scrupuleusement la structure et le ton demandés. Respecte la structure : accroche (ligne 1) → saut de ligne → corps (phrases courtes, 2-3 max par bloc, saut de ligne entre chaque) → saut de ligne → hashtags (3 max, dernière ligne).
2. "image_prompt": Le prompt en anglais pour le générateur d'image (basé sur les directives visuelles du persona).

Réponds UNIQUEMENT avec le code JSON, sans aucun texte avant ou après."""
    else:
        prompt = f"""Sujet du post : {topic.get('titre', topic.get('topic', ''))}
Angle spécifique : {topic.get('angle', '')}
Promesse au lecteur : {topic.get('promesse', '')}
Secteur d'inspiration : {topic.get('secteur', '')}
Problème traité : {topic.get('probleme', '')}
Jour de publication prévu : {topic.get('jour', 'non défini')}

EXEMPLES DE POSTS À IMITER (structure, ton, longueur) :
{persona.get('examples', '')}

Tu dois OBLIGATOIREMENT répondre au format JSON.
Ton JSON doit contenir exactement ces deux clés :
1. "post_content": Le texte complet du post LinkedIn ({min_words}-{max_words} mots), respectant scrupuleusement la structure et le ton demandés. Respecte la structure : accroche (ligne 1) → saut de ligne → corps (phrases courtes, 2-3 max par bloc, saut de ligne entre chaque) → saut de ligne → hashtags (3 max, dernière ligne).
2. "image_prompt": Le prompt en anglais pour le générateur d'image (basé sur les directives visuelles du persona).

Réponds UNIQUEMENT avec le code JSON, sans aucun texte avant ou après."""

    if indication:
        prompt += f"\n\nINDICATION IMPORTANTE DE L'UTILISATEUR POUR CETTE RÉÉCRITURE :\n{indication}\nPrends IMPÉRATIVEMENT en compte cette remarque pour générer ce post."

    try:
        response = groq_request(prompt, system, max_tokens=1000, temperature=0.5)
        if not response:
            return None

        # Nettoyage et parsing du JSON
        clean_json = response.strip()
        import re
        
        # Étape 1 : Si le LLM a ajouté des emojis ou texte avant le JSON, extraire de { à }
        first_brace = clean_json.find('{')
        last_brace = clean_json.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            clean_json = clean_json[first_brace:last_brace + 1]
        
        # Étape 2 : Strip markdown code fences si présents
        if clean_json.startswith("```"):
            clean_json = re.sub(r'^```\w*\n?', '', clean_json)
            clean_json = re.sub(r'\n?```\s*$', '', clean_json)
        clean_json = clean_json.strip()
        
        # Étape 3 : Extraire le bloc JSON même si du texte traîne autour
        json_match = re.search(r'\{[\s\S]*\}', clean_json)
        if json_match:
            clean_json = json_match.group(0)
        clean_json = clean_json.strip()

        try:
            parsed_data = json.loads(clean_json)
            post = parsed_data.get("post_content", "")
            image_prompt = parsed_data.get("image_prompt", "")
            if not post:
                logging.error("[LINKEDIN] JSON parsé mais 'post_content' vide. Fallback raw.")
                post = response
                image_prompt = ""
        except json.JSONDecodeError as e:
            # Tentative : échapper les nouvelles lignes dans les valeurs string
            try:
                fixed = re.sub(r'(?<=": ")([^"]*?)(?="\s*[,}])', lambda m: m.group(0).replace('\n', '\\n'), clean_json, flags=re.DOTALL)
                parsed_data = json.loads(fixed)
                post = parsed_data.get("post_content", "")
                image_prompt = parsed_data.get("image_prompt", "")
            except Exception:
                logging.error(f"[LINKEDIN] Parsing JSON échoué ({e}). Fallback raw. Réponse LLM: {response[:200]}")
                post = response
                image_prompt = ""

        date_str = datetime.now().strftime("%Y-%m-%d")
        folder_name = f"{date_str}_{slugify(topic['titre'])}"
        
        # Enregistrement dans le bon dossier (par compte ou global)
        if folder_path:
            folder = Path(folder_path)
        elif account_id:
            content_dir = Path("accounts") / str(account_id) / "content"
            folder = content_dir / folder_name
        else:
            content_dir = Path("content")
            folder = content_dir / folder_name
        
        folder.mkdir(parents=True, exist_ok=True)

        (folder / "linkedin_post.txt").write_text(post, encoding="utf-8")
        
        meta_data = {**topic, "persona": format_id, "status": "pending", "published": False, "folder": str(folder), "account_id": account_id, "platform": "linkedin"}
        if image_prompt:
            meta_data["image_prompt"] = image_prompt
            
        (folder / "meta.json").write_text(
            json.dumps(meta_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        # Log dans Google Sheets (mention si réécriture)
        sheet_msg = post[:100] + "..."
        if indication:
            sheet_msg = "[REGEN] " + sheet_msg
        log_to_sheet("Redactions", [datetime.now().strftime("%Y-%m-%d"), topic["titre"], sheet_msg])
        
        print(f"✅ [{topic.get('format_nom', 'Post')}] rédigé → {folder}")
        return str(folder)
        
    except Exception as e:
        logging.error(f"Erreur rédaction post : {e}")
        print(f"❌ Erreur lors de la rédaction : {e}")
        return None

def regenerate_post(folder_name, indication=None):
    """Régènère un post existant DANS LE MÊMe DOSSIER.
    
    Contrairement à write_linkedin_post, cette fonction écrase le fichier
    texte dans le dossier existant sans en créer un nouveau.
    L'image_prompt existant est préservé si le LLM n'en génère pas un nouveau.
    """
    try:
        folder = Path(folder_name)
        meta_path = folder / "meta.json"
        
        if not meta_path.exists():
            raise FileNotFoundError("Méta-données introuvables pour ce post.")
            
        topic = json.loads(meta_path.read_text(encoding="utf-8"))
        existing_image_prompt = topic.get("image_prompt", "")
        format_id = topic.get("format_id", "conseil")
        account_id = topic.get("account_id")
        
        persona = get_persona(format_id, account_id=account_id)
        if not persona:
            raise ValueError(f"Persona '{format_id}' introuvable.")

        system = persona["system_prompt"]
        config = persona["config"]
        min_words = config.get("min_words", 150)
        max_words = config.get("max_words", 220)

        prompt = f"""Sujet du post : {topic.get('titre', '')}
Angle spécifique : {topic.get('angle', '')}
Promesse au lecteur : {topic.get('promesse', '')}

Tu dois OBLIGATOIREMENT répondre au format JSON.
Ton JSON doit contenir exactement ces deux clés :
1. "post_content": Le texte complet du post LinkedIn ({min_words}-{max_words} mots).
2. "image_prompt": Le prompt en anglais pour le générateur d'image.

Réponds UNIQUEMENT avec le code JSON, sans aucun texte avant ou après."""

        if indication:
            prompt += f"\n\nINDICATION IMPORTANTE DE L'UTILISATEUR POUR CETTE RÉÉCRITURE :\n{indication}\nPrends IMPÉRATIVEMENT en compte cette remarque."

        from agents.agent_topics import groq_request
        response = groq_request(prompt, system, max_tokens=1000, temperature=0.5)
        if not response:
            raise RuntimeError("Pas de réponse du LLM")

        # Parsing JSON
        clean_json = response.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json.split("```json")[1]
        if clean_json.endswith("```"):
            clean_json = clean_json.rsplit("```", 1)[0]
        clean_json = clean_json.strip()

        try:
            parsed = json.loads(clean_json)
            post = parsed.get("post_content", response)
            new_image_prompt = parsed.get("image_prompt", "")
        except json.JSONDecodeError:
            logging.error("[LINKEDIN REGEN] Parsing JSON échoué. Fallback raw.")
            post = response
            new_image_prompt = ""

        # Écriture du post dans le même dossier
        (folder / "linkedin_post.txt").write_text(post, encoding="utf-8")

        # Préservation/mise à jour de l'image_prompt dans meta.json
        if new_image_prompt:
            topic["image_prompt"] = new_image_prompt
        elif existing_image_prompt:
            topic["image_prompt"] = existing_image_prompt  # préservation
        meta_path.write_text(json.dumps(topic, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"✅ Post LinkedIn régénéré dans {folder}")
        return str(folder)
    except Exception as e:
        logging.error(f"Erreur regenerate_post : {e}")
        raise e

def write_validated_topics():
    """Rédige les sujets validés dans topics_pending.json."""
    try:
        pending_path = Path("data/topics_pending.json")
        if not pending_path.exists():
            print("⚠️ Aucun sujet trouvé — lance d'abord 'python main.py'")
            return []

        topics = json.loads(pending_path.read_text(encoding="utf-8"))
        validated = [t for t in topics if t.get("validated") is True]

        if not validated:
            print("⚠️ Aucun sujet validé — utilise le dashboard pour valider")
            return []

        print(f"✍️ Rédaction de {len(validated)} post(s)...")
        folders = []
        for topic in validated:
            folder = write_linkedin_post(topic)
            if folder:
                folders.append(folder)
        return folders
    except Exception as e:
        logging.error(f"Erreur dans write_validated_topics : {e}")
        return []

if __name__ == "__main__":
    write_validated_topics()
