import sys
import io
# if sys.platform == "win32":
#     try:
#         if hasattr(sys.stdout, "buffer") and sys.stdout.buffer:
#             sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
#         if hasattr(sys.stderr, "buffer") and sys.stderr.buffer:
#             sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
#     except (ValueError, AttributeError):
#         pass
import subprocess
import requests
import json
import os
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from core.models import AgentResult
from core.config import Config
from core.logger import get_node_logger

logger = get_node_logger("image_creator")

# Tous les sous-scripts sont co-localisés dans ce même dossier
_AGENT_DIR = Path(__file__).resolve().parent
GEMINI_SCRIPT   = str(_AGENT_DIR / "gemini_automation.py")
GEMINI_ENGINE   = str(_AGENT_DIR / "gemini_engine.py")
USER_PHOTO_PATH = str(_AGENT_DIR / "JM.png")

# Personas qui utilisent la photo de l'utilisateur selon la plateforme
_USER_PHOTO_PERSONAS = {
    "facebook": ["cta", "kebane_story", "kebane_verdict", "mini_formation"],
    "linkedin": ["coulisses", "networker"],
    "twitter":  [],
}

_USER_PHOTO_PATHS = {
    "mini_formation": r"D:\Content_Machine\mon_image.png",
}

_PLATFORM_BASE_DIRS = {
    "facebook": Path("d:/Content_Machine/machines/facebook_machine"),
    "linkedin": Path("d:/Content_Machine/machines/linkedin_machine"),
    "twitter":  Path("d:/Content_Machine/machines/twitter_machine"),
}

_PLATFORM_LABELS = {
    "facebook": "post Facebook",
    "linkedin": "article LinkedIn professionnel",
    "twitter":  "tweet Twitter",
}

def _get_image_mode(persona: str, post_text: str, platform: str = "facebook") -> str:
    persona_lower = (persona or "").lower()
    user_photo_personas = _USER_PHOTO_PERSONAS.get(platform, _USER_PHOTO_PERSONAS["facebook"])
    if persona_lower in user_photo_personas:
        return "user_photo"
    return "generated"

def _generate_image_concept(post_text: str, topic: str, persona: str, platform: str = "facebook", account_id: str = None) -> str:
    # Charger le system prompt selon la plateforme et le compte (avec fallbacks)
    platform_base = _PLATFORM_BASE_DIRS.get(platform, _PLATFORM_BASE_DIRS["facebook"])
    
    # Chercher d'abord un image_system_prompt spécifique au compte
    acc_str = str(account_id) if account_id else "1"
    image_system_prompt_path = platform_base / "accounts" / acc_str / "persona" / "_shared" / "image_system_prompt.md"
    if not image_system_prompt_path.exists():
        # Fallback vers le prompt partagé de la plateforme
        image_system_prompt_path = platform_base / "persona" / "_shared" / "image_system_prompt.md"
    if not image_system_prompt_path.exists():
        # Fallback vers Facebook
        image_system_prompt_path = _PLATFORM_BASE_DIRS["facebook"] / "persona" / "_shared" / "image_system_prompt.md"
    system_prompt = ""
    if image_system_prompt_path.exists():
        system_prompt = image_system_prompt_path.read_text(encoding="utf-8")

    platform_label = _PLATFORM_LABELS.get(platform, "post")
    user_prompt = f"""Génère un prompt Gemini pour illustrer ce contenu.

PLATEFORME : {platform_label}
PERSONA : {persona}
SUJET : {topic}

EXTRAIT DU CONTENU :
{post_text[:500]}

RÈGLES :
- Réponds UNIQUEMENT avec le prompt complet, sans introduction ni explication
- Commence OBLIGATOIREMENT par : Génère l'image suivante :
- Décris une scène professionnelle qui illustre viscéralement le message du post
- Le ou les personnages doivent être universels (pas de culture, ethnie ou géographie spécifique imposée)
- Adéque ton style visuel à la plateforme : {platform_label}
- Précise le cadrage, la lumière, le style photographique
- Langue d'affichage : français
- 2 à 5 phrases en français"""

    from core.groq_router import call_groq_image
    try:
        concept = call_groq_image(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.9,
            max_tokens=600
        )
        if concept and len(concept) > 10:
            logger.info(f"Prompt Gemini généré (platform={platform}): {concept[:80]}...")
            # S'assurer que le prompt commence bien par le préfixe Gemini
            if not concept.strip().startswith("Génère l'image suivante"):
                concept = f"Génère l'image suivante : {concept.strip()}"
            return concept.strip()
    except Exception as e:
        logger.warning(f"Groq concept failed: {e}")

    logger.info("Using fallback concept logic")
    return "Photorealistic portrait of a confident professional at work, modern office, highly detailed, no text"

def _run_subprocess_gemini(script_path: str, args: list) -> str:
    cmd = ["python", script_path] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=600)
        for line in result.stdout.splitlines():
            if "[RESULT]" in line:
                url = line.split("[RESULT]", 1)[1].strip()
                if url.startswith("http"):
                    return url
        logger.error(f"No [RESULT] found. STDOUT: {result.stdout[:2000]}")
    except subprocess.TimeoutExpired:
        logger.error("Timeout during image script execution")
    except Exception as e:
        logger.error(f"Error calling {script_path}: {e}")
    return None

def run_image_creator(folder_path: str, platform: str = None, hint: str = None, account_id: str = None, existing_image_path: str = None) -> AgentResult:
    """Génère l'image pour un post donné.
    
    Args:
        folder_path: Chemin du dossier contenant le post
        platform: Plateforme cible (facebook, linkedin, twitter)
        hint: Indication optionnelle de l'utilisateur pour guider le style visuel
        account_id: ID du compte pour charger le bon image_system_prompt
        existing_image_path: Chemin vers une image existante à modifier (mode modify)
    """
    if not Config.POST_IMAGE_ENABLED:
        logger.info("Image generation disabled in config.")
        return AgentResult.ok({"status": "disabled"})

    folder = Path(folder_path)
    if not folder.exists():
        return AgentResult.fail("Dossier post introuvable")

    # Recherche du fichier texte selon la plateforme (multi-plateforme)
    _POST_TEXT_FILES = [
        "facebook_post.txt", "linkedin_post.txt", "twitter_post.txt",
        "tweet_post.txt", "post_text.txt", "content.txt", "post.txt"
    ]
    post_file = None
    for fname in _POST_TEXT_FILES:
        candidate = folder / fname
        if candidate.exists():
            post_file = candidate
            break

    if not post_file:
        return AgentResult.fail("Texte du post absent")

    post_text = post_file.read_text(encoding="utf-8")
    meta_file = folder / "meta.json"
    meta = {}
    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))

    topic = meta.get("topic", "")
    persona = meta.get("persona", "")
    # Priorité: paramètre explicite > meta.json > défaut facebook
    effective_platform = platform or meta.get("platform", "facebook")
    effective_account_id = account_id or meta.get("account_id") or "1"
    mode = _get_image_mode(persona, post_text, effective_platform)

    concept = meta.get("image_prompt", "")
    if concept:
        logger.info(f"Utilisation du prompt pré-généré depuis meta.json: {concept[:80]}...")
        if not concept.strip().startswith("Génère l'image suivante"):
            concept = f"Génère l'image suivante : {concept.strip()}"
            
    if not concept:
        logger.warning(
            f"[IMAGE_CREATOR] ⚠️ Aucun image_prompt dans meta.json pour {folder.name}. "
            f"Fallback sur _generate_image_concept (post ancien ou LLM JSON raté). "
            f"Platform={effective_platform}, Account={effective_account_id}"
        )
        concept = _generate_image_concept(post_text, topic, persona, effective_platform, account_id=effective_account_id)

        
    if not concept:
        return AgentResult.fail("Impossible de générer le concept")

    # ── Injection du hint utilisateur (régénération guidée) ──
    if hint:
        concept = f"{concept}. Style supplémentaire demandé par l'utilisateur: {hint}"
        logger.info(f"[IMAGE_CREATOR] Hint injecté: {hint[:80]}")

    image_url = None

    # Mode modify avec image existante (uploadée depuis la librairie)
    if existing_image_path and Path(existing_image_path).exists():
        scene = concept.replace("Génère l'image suivante :", "").replace("Génère l'image suivante", "").strip()
        full_prompt = f"Modify this image to better illustrate the following content. Keep the main subject but adapt the style, background, or details to match: {scene}"
        logger.info(f"[IMAGE_CREATOR] Mode existing_image+modify: {existing_image_path}")
        image_url = _run_subprocess_gemini(GEMINI_ENGINE, [full_prompt, "--mode", "modify", "--image", existing_image_path])

    if mode == "user_photo":
        ref_path = _USER_PHOTO_PATHS.get(persona.lower(), USER_PHOTO_PATH)
        if Path(ref_path).exists():
            if persona.lower() == "mini_formation":
                scene = concept.replace("Génère l'image suivante :", "").replace("Génère l'image suivante", "").strip()
                full_prompt = (
                    "The person in the attached reference photo is the main character. "
                    "Keep their face, facial features, and head shape strictly identical. "
                    "Change only: clothing, posture, background/environment. "
                    "He is wearing a pristine white long-sleeved dress shirt, tailor-fitted, made of premium Egyptian cotton, "
                    "crisp and impeccably pressed with a stiff collar and no wrinkles. "
                    "It is worn untucked over dark jeans, with the top buttons left open "
                    "and the sleeves neatly rolled up to his forearms. "
                    "He wears a matching white fedora hat, perfectly angled, giving a sharp sophisticated look. "
                    f"{scene}"
                )
            else:
                full_prompt = f"{concept}. Professional realistic photo. No text."
            image_url = _run_subprocess_gemini(GEMINI_ENGINE, [full_prompt, "--mode", "modify", "--image", ref_path])
    
    if not image_url:
        # Le prompt est déjà complet (commence par "Génère l'image suivante :")
        full_prompt = concept
        image_url = _run_subprocess_gemini(GEMINI_ENGINE, [full_prompt])

    if not image_url:
        meta["image_failed"] = True
        meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return AgentResult.fail("Gemini Scripts ont échoué à renvoyer une URL")

    output_path = folder / "post_image.jpg"
    try:
        resp = requests.get(image_url, timeout=30)
        if resp.status_code == 200:
            output_path.write_bytes(resp.content)
            meta["post_image"] = "post_image.jpg"
            meta["image_url"] = image_url
            meta["image_failed"] = False
            meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            return AgentResult.ok({"image_url": image_url, "local_path": str(output_path)})
    except Exception as e:
        logger.error(f"Download error: {e}")
        return AgentResult.fail(f"Impossible de télécharger l'image depuis {image_url}")

    return AgentResult.fail("Échec silencieux lors du téléchargement")
