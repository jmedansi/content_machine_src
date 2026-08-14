# li_adapter.py — Adapter LinkedIn pour Common Core
# Usage: from common.adapters.li_adapter import LIAdapter

import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT_DIR))
sys.path.insert(0, str(_ROOT_DIR / "common"))

from common.services.text_generator import TextGenerator
from common.utils.persona_loader import load_personas

logger = logging.getLogger(__name__)


class LIAdapter:
    """Adapter LinkedIn - utilise le Common Core pour la génération."""
    
    def __init__(self, account_id: int = None):
        self.platform = "linkedin"
        self.account_id = account_id
        self.generator = TextGenerator(platform=self.platform)
        self.personas = load_personas(self.platform, account_id)
        logger.info(f"[LIAdapter] Init avec {len(self.personas)} personas")
    
    def generate_post(self, topic: str, persona: str, angle: str = "", 
                   promesse: str = "", secteur: str = "", probleme: str = "") -> Dict[str, Any]:
        """
        Génère un post LinkedIn.
        
        Args:
            topic: Sujet du post
            persona: Nom du persona
            angle: Angle spécifique
            promesse: Promesse au lecteur
            secteur: Secteur d'inspiration
            probleme: Problème traité
        
        Returns:
            {"success": bool, "text": str, "persona": str, "error": str}
        """
        p_config = {}
        for p in self.personas:
            if p.get("name") == persona:
                p_config = p
                break
        
        prompt = f"""Sujet du post : {topic}
Angle spécifique : {angle}
Promesse au lecteur : {promesse}
Secteur d'inspiration : {secteur}
Problème traité : {probleme}

Rédige le post LinkedIn complet."""

        system = p_config.get("system_prompt", "")
        min_words = p_config.get("min_words", 150)
        max_words = p_config.get("max_words", 220)
        
        if system:
            prompt += f"\n\nLe post doit faire entre {min_words} et {max_words} mots."

        result = self.generator.generate(
            prompt=prompt,
            persona=persona,
            system=system
        )
        
        return result
    
    def generate_carousel(self, topic: str, persona: str = "carousel_pro") -> Dict[str, Any]:
        """Génère le contenu d'un carousel PDF."""
        # Le carousel est un type spécial de post LI
        result = self.generate_post(topic=topic, persona=persona)
        return result
    
    def get_personas(self) -> list:
        """Retourne les personas disponibles."""
        return self.personas


# === FONCTIONS UTILITAIRES ===

def generate_post(topic: str, persona: str = "b2b_expert", 
                angle: str = "", account_id: int = None) -> str:
    """Génère un post LinkedIn rapidement."""
    adapter = LIAdapter(account_id)
    result = adapter.generate_post(topic, persona, angle=angle)
    return result.get("text", "")


def get_personas(account_id: int = None) -> list:
    """Liste les personas LinkedIn."""
    return load_personas("linkedin", account_id)


if __name__ == "__main__":
    adapter = LIAdapter()
    print(f"Personas: {[p['name'] for p in adapter.get_personas()]}")