# persona_loader.py — Chargeur universel de personas
# Usage: from common.utils.persona_loader import load_personas, get_persona

import json
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT_DIR))

logger = logging.getLogger(__name__)

# Mapping plateforme -> chemins
try:
    from core.paths import PLATFORM_BASE as PLATFORM_PATHS
except ImportError:
    PLATFORM_PATHS = {
        "facebook": _ROOT_DIR / "machines" / "facebook_machine",
        "linkedin": _ROOT_DIR / "machines" / "linkedin_machine",
        "twitter": _ROOT_DIR / "machines" / "twitter_machine",
    }


def _get_personas_dir(platform: str, account_id: int = None) -> Path:
    """Retourne le dossier personas selon plateforme et account."""
    base = PLATFORM_PATHS.get(platform)
    if not base:
        raise ValueError(f"Plateforme inconnue: {platform}")
    
    # Si account_id spécifié, chercher dans accounts/<id>/persona/
    if account_id:
        acc_dir = base / "accounts" / str(account_id)
        if acc_dir.exists():
            return acc_dir / "persona"
    
    # Par défaut: persona à la racine de la plateforme
    return base / "persona"


def load_personas(platform: str, account_id: int = None) -> List[Dict[str, Any]]:
    """
    Charge tous les personas pour une plateforme (et optionnellement un account).
    
    Returns:
        [{"name": str, "config": dict, "system_prompt": str, ...}]
    """
    persona_dir = _get_personas_dir(platform, account_id)
    
    if not persona_dir.exists():
        logger.warning(f"[persona_loader] Dossier introuvable: {persona_dir}")
        return []
    
    personas = []
    for folder in sorted(persona_dir.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name.startswith("_") or folder.name.startswith("."):
            continue
        
        try:
            # Charger config.json
            config = {}
            config_file = folder / "config.json"
            if config_file.exists():
                config = json.loads(config_file.read_text(encoding="utf-8"))
            
            # Charger system_prompt.md
            system_prompt = ""
            prompt_file = folder / "system_prompt.md"
            if prompt_file.exists():
                system_prompt = prompt_file.read_text(encoding="utf-8")
            
            # Charger examples.md
            examples = ""
            examples_file = folder / "examples.md"
            if examples_file.exists():
                examples = examples_file.read_text(encoding="utf-8")
            
            personas.append({
                "name": folder.name,
                "config": config,
                "system_prompt": system_prompt,
                "examples": examples,
                "display_name": config.get("display_name", config.get("nom_persona", folder.name.replace("_", " ").title())),
                "min_words": config.get("min_words", config.get("target_words", 150)),
                "max_words": config.get("max_words", config.get("target_words", 300)),
                "ton": config.get("ton", config.get("tone", "")),
            })
        except Exception as e:
            logger.error(f"[persona_loader] Erreur {folder.name}: {e}")
    
    logger.info(f"[persona_loader] {len(personas)} personas for {platform}" + (f" (accounts/{account_id})" if account_id else ""))
    return personas


def get_persona(platform: str, name: str, account_id: int = None) -> Optional[Dict[str, Any]]:
    """Retourne un persona spécifique par son nom."""
    personas = load_personas(platform, account_id)
    for p in personas:
        if p["name"] == name:
            return p
    return None


def list_platforms() -> list:
    """Liste les plateformes disponibles."""
    return list(PLATFORM_PATHS.keys())