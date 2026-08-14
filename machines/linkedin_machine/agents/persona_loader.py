# persona_loader.py — Chargement dynamique des personas pour LinkedIn
import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)


def load_personas(account_id: int = None):
    """Charge tous les personas depuis le dossier persona/.
    
    Args:
        account_id: Si fourni, charge les personas depuis acc_{account_id}/persona/
                   Sinon, utilise le dossier global persona/
    """
    base_dir = Path(__file__).resolve().parent.parent
    if account_id:
        persona_dir = base_dir / "accounts" / str(account_id) / "persona"
    else:
        persona_dir = base_dir / "persona"
    
    if not persona_dir.exists():
        logging.warning(f"Dossier persona introuvable: {persona_dir}")
        return []
    
    personas = []
    for folder in persona_dir.iterdir():
        if not folder.is_dir():
            continue
        if folder.name.startswith('_'):
            continue
        
        config_file = folder / "config.json"
        if not config_file.exists():
            continue
        
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
            
            system_prompt_file = folder / "system_prompt.md"
            system_prompt = system_prompt_file.read_text(encoding="utf-8") if system_prompt_file.exists() else ""
            
            examples_file = folder / "examples.md"
            examples = examples_file.read_text(encoding="utf-8") if examples_file.exists() else ""
            
            format_file = folder / "format.json"
            format_data = json.loads(format_file.read_text(encoding="utf-8")) if format_file.exists() else None
            
            persona = {
                "name": folder.name,
                "config": config,
                "format": format_data,
                "system_prompt": system_prompt,
                "examples": examples,
            }
            personas.append(persona)
        except Exception as e:
            logging.error(f"Erreur chargement persona {folder.name}: {e}")
    
    logging.info(f"Chargé {len(personas)} personas: {[p['name'] for p in personas]}")
    return personas


def get_persona(name: str, account_id: int = None):
    """Charge un persona spécifique par son nom.
    
    Args:
        name: Nom du persona
        account_id: Si fourni, charge depuis acc_{account_id}/persona/
    """
    personas = load_personas(account_id)
    for p in personas:
        if p["name"] == name:
            return p
    return None


def get_active_personas(account_id: int = None):
    """Retourne seulement les personas actifs (ceux sans prefix _).
    
    Args:
        account_id: Si fourni, charge depuis acc_{account_id}/persona/
    """
    return load_personas(account_id)


if __name__ == "__main__":
    for p in load_personas():
        print(f"- {p['name']}: {p['config'].get('display_name', p['name'])}")