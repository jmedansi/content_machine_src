# fb_adapter.py — Adapter Facebook pour Common Core
# Usage: from common.adapters.fb_adapter import FBAdapter

import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT_DIR))
sys.path.insert(0, str(_ROOT_DIR / "common"))

from common.services.text_generator import TextGenerator
from common.utils.persona_loader import load_personas

logger = logging.getLogger(__name__)


class FBAdapter:
    """Adapter Facebook - utilise le Common Core pour la génération."""
    
    def __init__(self, account_id: int = None):
        self.platform = "facebook"
        self.account_id = account_id
        self.generator = TextGenerator(platform=self.platform)
        self.personas = load_personas(self.platform, account_id)
        logger.info(f"[FBAdapter] Init avec {len(self.personas)} personas")
    
    def generate_post(self, topic: str, persona: str, context: str = "", objectif: str = "engagement") -> Dict[str, Any]:
        """
        Génère un post Facebook.
        
        Args:
            topic: Sujet du post
            persona: Nom du persona à utiliser
            context: Contexte adicional
            objectif: Objectif (engagement, conversion, autorité)
        
        Returns:
            {"success": bool, "text": str, "persona": str, "error": str}
        """
        # Trouver le persona pour avoir ses params
        p_config = {}
        for p in self.personas:
            if p.get("name") == persona:
                p_config = p
                break
        
        # Construire le prompt
        prompt = f"""Sujet: {topic}
Contexte: {context}
Objectif: {objectif}

Rédige un post Facebook percutant selon les instructions du persona."""

        system = p_config.get("system_prompt", "")
        min_words = p_config.get("min_words", 150)
        max_words = p_config.get("max_words", 300)
        
        if system:
            prompt += f"\n\nLe post doit faire entre {min_words} et {max_words} mots."

        result = self.generator.generate(
            prompt=prompt,
            persona=persona,
            system=system
        )
        
        return result
    
    def get_personas(self) -> list:
        """Retourne les personas disponibles."""
        return self.personas
    
    def get_persona_config(self, name: str) -> Optional[Dict]:
        """Retourne la config d'un persona spécifique."""
        for p in self.personas:
            if p.get("name") == name:
                return p
        return None


# === FONCTIONS UTILITAIRES ===

def generate_post(topic: str, persona: str = "post_court", context: str = "", 
                account_id: int = None) -> str:
    """Génère un post Facebook rapidement."""
    adapter = FBAdapter(account_id)
    result = adapter.generate_post(topic, persona, context)
    return result.get("text", "")


def get_personas(account_id: int = None) -> list:
    """Liste les personas Facebook."""
    return load_personas("facebook", account_id)


if __name__ == "__main__":
    # Test
    adapter = FBAdapter()
    print(f"Personas: {[p['name'] for p in adapter.get_personas()]}")
    
    result = adapter.generate_post(
        topic="L'IA va-t-elle remplacer les devs?",
        persona="avis_tranches"
    )
    print(f"\n--- Résultat ---\n{result.get('text', result.get('error', 'Erreur')[:200]}")