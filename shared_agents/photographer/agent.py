import sys
import re
import json
import subprocess
import requests
from pathlib import Path

# Add core to path if needed
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from core.models import AgentResult
from core.config import Config
from core.logger import get_node_logger

logger = get_node_logger("photographer")

# Reuse the existing Gemini engine bridge
_IMAGE_CREATOR_DIR = Path("d:/Content_Machine/machines/facebook_machine/agents/image_creator")
GEMINI_ENGINE = str(_IMAGE_CREATOR_DIR / "gemini_engine.py")
PROMPTS_DB_PATH = Path("d:/image_prompt_generator/prompts_data.json")

def _load_best_examples(category: str, top_n: int = 2) -> str:
    if not PROMPTS_DB_PATH.exists():
        logger.warning(f"Database {PROMPTS_DB_PATH} not found.")
        return ""
    try:
        data = json.loads(PROMPTS_DB_PATH.read_text(encoding="utf-8"))
        categories = data.get("categories", {})
        prompts = categories.get(category, [])
        if not prompts:
            return ""
        
        # Sort by community_rating (e.g., "9.2/10" -> 9.2)
        def parse_rating(rating_str):
            try:
                return float(rating_str.split("/")[0])
            except:
                return 0.0

        sorted_prompts = sorted(prompts, key=lambda x: parse_rating(x.get("community_rating", "0")), reverse=True)
        best = sorted_prompts[:top_n]
        
        examples_str = ""
        for p in best:
            examples_str += f"- Exemple (Note: {p.get('community_rating')}): \"{p.get('text')}\"\n"
        return examples_str
    except Exception as e:
        logger.error(f"Error loading examples from JSON: {e}")
        return ""

def _clean_text_for_json(raw: str) -> str:
    if not raw:
        return ""
    text = raw.strip()
    text = re.sub(r"```(?:json|js|python)?\n", "", text, flags=re.I)
    text = re.sub(r"\n```", "", text)
    return text


def _extract_json(raw: str):
    text = _clean_text_for_json(raw)
    if not text:
        return None

    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start >= 0 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                continue
    return None


def _parse_num_images_from_config(config_text: str, config_json: dict = None) -> int:
    if isinstance(config_json, dict):
        num = config_json.get("num_images") or config_json.get("image_count") or config_json.get("nb_images")
        if isinstance(num, int) and num > 0:
            return num
        if isinstance(num, str) and num.isdigit():
            return int(num)

    if config_text:
        match = re.search(r"generation\s*[:=]\s*(\d+)\s*-\s*(\d+)", config_text, flags=re.I)
        if match:
            return int(match.group(2))
        match = re.search(r"generation\s*[:=]\s*(\d+)", config_text, flags=re.I)
        if match:
            return int(match.group(1))
        match = re.search(r"(\d+)\s*(?:variants|images?)", config_text, flags=re.I)
        if match:
            return int(match.group(1))
    return 1


def _generate_single_photography_prompt(persona_name: str, config_text: str, user_topic: str) -> str:
    examples = _load_best_examples(persona_name)
    
    system_prompt = f"""Tu es le Directeur Photographique d'IncidenX.
Ta mission est de rédiger LE prompt parfait (en ANGLAIS) pour le générateur d'images.

# RÈGLES DE DIRECTION ARTISTIQUE OBLIGATOIRES
{config_text if config_text else "Pas de config trouvée, applique un style photoréaliste de haute qualité."}

# EXEMPLES D'EXCELLENCE DE LA COMMUNAUTÉ (Inspiration syntaxique)
{examples if examples else "Pas d'exemples trouvés. Utilise un langage descriptif technique photographique (lighting, camera lens, mood)."}
"""
    
    topic_context = user_topic if user_topic else "Invente un sujet adapté aux sujets de prédilection de ce persona"
    
    user_prompt = f"""
Rédige le prompt final exact (en ANGLAIS) à envoyer au générateur d'image.
Sujet demandé par l'utilisateur : {topic_context}

ATTENTION (CRITIQUE POUR LA GÉNÉRATION) :
- Commence OBLIGATOIREMENT ta réponse par : Génère l'image suivante :
- Fais un choix clair : si la config propose plusieurs couleurs (ex: pastel ou noir), CHOISIS-EN UNE SEULE. Ne demande pas les deux en même temps.
- Sois cohérent sur la caméra : ne demande pas "f/11 (netteté totale)" ET "shallow depth of field (flou d'arrière-plan)" dans la même phrase. Fais un choix technique logique.
- Ne mets JAMAIS d'intentions marketing. Seulement de la description visuelle pure (lumière, texture, objectif, cadrage).
- Le prompt généré doit être en anglais, très détaillé, comme les exemples fournis.
"""

    from core.groq_router import call_groq_image
    try:
        concept = call_groq_image(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=600
        )
        if concept and len(concept) > 10:
            if not concept.strip().startswith("Génère l'image suivante"):
                concept = f"Génère l'image suivante : {concept.strip()}"
            logger.info(f"Generated photography prompt: {concept[:100]}...")
            return concept.strip()
    except Exception as e:
        logger.warning(f"Groq photography prompt failed: {e}")
        
    return "Génère l'image suivante : A highly detailed professional photograph, studio lighting, 8k resolution."


def _generate_photography_prompts(persona_name: str, config_text: str, user_topic: str, count: int) -> list:
    """Generate main + variant prompts. For count > 1, uses copy-paste strategy."""
    if count <= 1:
        return [_generate_single_photography_prompt(persona_name, config_text, user_topic)]

    examples = _load_best_examples(persona_name)
    system_prompt = f"""Tu es le Directeur Photographique d'IncidenX.
Ta mission est de rédiger les prompts parfaits (en ANGLAIS) pour le générateur d'images.

# RÈGLES DE DIRECTION ARTISTIQUE OBLIGATOIRES
{config_text if config_text else "Pas de config trouvée, applique un style photoréaliste de haute qualité."}

# EXEMPLES D'EXCELLENCE DE LA COMMUNAUTÉ (Inspiration syntaxique)
{examples if examples else "Pas d'exemples trouvés. Utilise un langage descriptif technique photographique (lighting, camera lens, mood)."}
"""
    
    topic_context = user_topic if user_topic else 'Invente un sujet adapté aux sujets de prédilection de ce persona'
    
    user_prompt = f"""
Tu vas générer {count} prompts : 
1. UN PROMPT PRINCIPAL : photo complète de face (cue de face complète, l'image de référence)
2. {count - 1} PROMPTS DE VARIANTE : modifications/variations de cette photo principale (angles différents, close-up, etc.)

Format JSON strict, pas d'explication :
{{
  "main": "Génère l'image suivante : [description photo principale de face complète]",
  "variants": [
    "Modifie cette image : [variante 1]",
    "Modifie cette image : [variante 2]",
    ...
  ]
}}

Sujet : {topic_context}

CRITIQUE : 
- Le prompt "main" doit générer une photo FRONTALE, complète de face
- Les prompts "variants" doivent être des MODIFICATIONS applicables à l'image principale (angles, zoom, style)
"""

    from core.groq_router import call_groq_image
    try:
        raw_output = call_groq_image(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.75,
            max_tokens=800
        )
        if raw_output and len(raw_output) > 20:
            parsed = _extract_json(raw_output)
            if isinstance(parsed, dict):
                main_prompt = parsed.get("main", "")
                variants = parsed.get("variants", [])
                
                if isinstance(main_prompt, str) and main_prompt.strip():
                    if not main_prompt.strip().startswith("Génère l'image suivante"):
                        main_prompt = f"Génère l'image suivante : {main_prompt.strip()}"
                    
                    # Format variants: prepend "Modifie cette image" if not present
                    formatted_variants = []
                    for v in variants:
                        if isinstance(v, str):
                            if not v.strip().startswith("Modifie cette image"):
                                formatted_variants.append(f"Modifie cette image : {v.strip()}")
                            else:
                                formatted_variants.append(v.strip())
                    
                    result = [main_prompt] + formatted_variants[:count-1]
                    if len(result) >= count:
                        logger.info(f"Generated main + {len(result)-1} variant prompts from JSON output.")
                        return result[:count]
    except Exception as e:
        logger.warning(f"Groq main+variant prompt generation failed: {e}")

    # Fallback: generate single and duplicate
    single_prompt = _generate_single_photography_prompt(persona_name, config_text, user_topic)
    return [single_prompt] * count

def _run_subprocess_gemini(script_path: str, args: list) -> str:
    cmd = ["python", script_path] + args
    try:
        logger.info(f"Running Gemini engine: {' '.join(cmd[:3])}...")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=600)
        for line in result.stdout.splitlines():
            if "[RESULT]" in line:
                url = line.split("[RESULT]", 1)[1].strip()
                if url.startswith("http"):
                    return url
        logger.error(f"No [RESULT] found. STDOUT: {result.stdout[:2000]}")
    except Exception as e:
        logger.error(f"Error calling {script_path}: {e}")
    return None

def run_photographer(folder_path: str) -> AgentResult:
    """Agent Photographer: Visual-First pipeline."""
    folder = Path(folder_path)
    if not folder.exists():
        return AgentResult.fail("Dossier introuvable")

    meta_file = folder / "meta.json"
    meta = {}
    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))

    persona = meta.get("persona", "")
    topic = meta.get("topic", "")
    platform = meta.get("platform", "facebook")
    account_id = meta.get("account_id")

    # Load persona config — cherche dans le compte de l'utilisateur, fallback compte 2
    acc_str = str(account_id) if account_id else "2"
    platform_base = Path(f"d:/Content_Machine/machines/{platform}_machine")
    if not platform_base.exists():
        platform_base = Path("d:/Content_Machine/machines/facebook_machine")

    config_path = platform_base / "accounts" / acc_str / "persona" / persona / "config.md"
    if not config_path.exists():
        config_path = Path("d:/Content_Machine/machines/facebook_machine/accounts/2/persona") / persona / "config.md"

    config_text = ""
    config_json = {}
    if config_path.exists():
        config_text = config_path.read_text(encoding="utf-8")

    config_json_path = platform_base / "accounts" / acc_str / "persona" / persona / "config.json"
    if config_json_path.exists():
        try:
            config_json = json.loads(config_json_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Unable to read persona config.json: {e}")

    num_images = _parse_num_images_from_config(config_text, config_json)
    if num_images < 1:
        num_images = 1

    logger.info(f"Photographer starting | persona={persona} | topic={topic} | account={acc_str} | platform={platform} | num_images={num_images}")

    prompts = _generate_photography_prompts(persona, config_text, topic, num_images)
    meta["photographer_prompt"] = prompts[0] if prompts else ""
    meta["photographer_prompts"] = prompts
    meta["image_count"] = len(prompts)

    # Clean old images first
    if (folder / "post_image.jpg").exists():
        (folder / "post_image.jpg").unlink()
    image_folder = folder / "images"
    image_folder.mkdir(exist_ok=True)
    for existing in image_folder.iterdir():
        if existing.is_file():
            existing.unlink()

    images_meta = []
    main_image_local_path = None
    
    for idx, prompt in enumerate(prompts, start=1):
        logger.info(f"Generating image {idx}/{len(prompts)}")
        
        # Image 1 (main): generate normally
        # Images 2+: use copy-paste strategy with main image as reference
        if idx == 1:
            image_url = _run_subprocess_gemini(GEMINI_ENGINE, [prompt])
            mode_label = "generate"
        else:
            if not main_image_local_path:
                logger.error(f"Main image path not available for variant {idx}, skipping")
                item = {
                    "index": idx,
                    "prompt": prompt,
                    "filename": f"images/post_image_{idx}.jpg",
                    "url": None,
                    "status": "failed"
                }
                images_meta.append(item)
                continue
            
            # Call Gemini in modify mode with the main image as reference
            image_url = _run_subprocess_gemini(
                GEMINI_ENGINE,
                ["--mode", "modify", "--reference-image", main_image_local_path, prompt]
            )
            mode_label = "modify (copy-paste)"
        
        item = {
            "index": idx,
            "prompt": prompt,
            "filename": f"images/post_image_{idx}.jpg",
            "url": image_url,
            "status": "failed"
        }

        if image_url:
            try:
                resp = requests.get(image_url, timeout=30)
                if resp.status_code == 200:
                    output_path = folder / item["filename"]
                    output_path.write_bytes(resp.content)
                    item["status"] = "generated"
                    
                    # Store main image path after first successful generation
                    if idx == 1:
                        main_image_local_path = str(output_path.absolute())
                        logger.info(f"Main image saved locally: {main_image_local_path}")
                    
                    logger.info(f"Image {idx} generated successfully via {mode_label}")
                else:
                    logger.error(f"Image download failed ({resp.status_code}) for image {idx} ({mode_label})")
            except Exception as e:
                logger.error(f"Download error for image {idx} ({mode_label}): {e}")
        else:
            logger.error(f"Gemini did not return a URL for image {idx} ({mode_label})")

        images_meta.append(item)

    success_count = sum(1 for item in images_meta if item["status"] == "generated")
    if success_count == 0:
        meta["image_failed"] = True
        meta["status"] = "error"
        meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return AgentResult.fail("Photographer: aucune image générée")

    first_success = next((item for item in images_meta if item["status"] == "generated"), images_meta[0])
    meta["post_image"] = first_success["filename"]
    meta["image_url"] = first_success["url"]
    meta["images"] = images_meta
    meta["image_failed"] = any(item["status"] != "generated" for item in images_meta)
    meta["has_image"] = True
    meta["visual_first_pipeline"] = True
    meta["status"] = "pending"
    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    _sync_to_db(platform, account_id, folder.name, persona, topic, str(folder / first_success["filename"]))

    logger.info(f"Photographer success! {success_count}/{len(images_meta)} images saved | status=pending")
    return AgentResult.ok({
        "image_urls": [item["url"] for item in images_meta if item["status"] == "generated"],
        "local_paths": [str(folder / item["filename"]) for item in images_meta if item["status"] == "generated"]
    })


def _sync_to_db(platform: str, account_id, folder_name: str, persona: str, topic: str, image_path: str):
    """Insère ou met à jour le post dans la base SQLite de la plateforme."""
    try:
        import sqlite3
        try:
            from core.paths import PLATFORM_DB
        except ImportError:
            _ROOT = Path(__file__).resolve().parent.parent.parent
            PLATFORM_DB = {
                "facebook": str(_ROOT / "machines" / "facebook_machine" / "data" / "leads_station.db"),
                "linkedin": str(_ROOT / "machines" / "linkedin_machine" / "data" / "leads_station.db"),
                "twitter":  str(_ROOT / "machines" / "twitter_machine" / "data" / "leads_station.db"),
            }
        db_path = PLATFORM_DB.get(platform, PLATFORM_DB.get("facebook"))
        if not Path(db_path).exists():
            logger.warning(f"DB not found: {db_path}")
            return

        acc_id = int(account_id) if account_id and str(account_id).isdigit() else None
        if not acc_id:
            logger.warning("account_id manquant, impossible de sync DB")
            return

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        existing = conn.execute(
            "SELECT id FROM posts WHERE account_id=? AND folder_name=?",
            (acc_id, folder_name)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE posts SET status='pending', has_image=1, image_filename='post_image.jpg' WHERE account_id=? AND folder_name=?",
                (acc_id, folder_name)
            )
            logger.info(f"DB updated: folder={folder_name} status=pending has_image=1")
        else:
            conn.execute("""
                INSERT INTO posts (account_id, folder_name, persona, topic, status, has_image, image_filename, published)
                VALUES (?, ?, ?, ?, 'pending', 1, 'post_image.jpg', 0)
            """, (acc_id, folder_name, persona, topic))
            logger.info(f"DB inserted: folder={folder_name} account_id={acc_id}")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"_sync_to_db error: {e}")

if __name__ == "__main__":
    # Test script if executed directly
    if len(sys.argv) > 1:
        print(run_photographer(sys.argv[1]))
    else:
        print("Usage: python agent.py <folder_path>")
