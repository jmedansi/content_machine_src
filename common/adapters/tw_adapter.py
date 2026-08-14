# tw_adapter.py — Adapter Twitter pour Common Core
# Usage: from common.adapters.tw_adapter import TWAdapter

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


class TWAdapter:
    """Adapter Twitter - utilise le Common Core pour la génération."""
    
    def __init__(self, account_id: int = None):
        self.platform = "twitter"
        self.account_id = account_id
        self.generator = TextGenerator(platform=self.platform)
        self.personas = load_personas(self.platform, account_id)
        logger.info(f"[TWAdapter] Init avec {len(self.personas)} personas")
    
    def generate_tweet(self, topic: str, persona: str = "hot_take", 
                    angle: str = "") -> Dict[str, Any]:
        """
        Génère un tweet (max 280 caractères).
        
        Args:
            topic: Sujet du tweet
            persona: Nom du persona (hot_take, thread_maker, quick_tip)
            angle: Angle spécifique
        
        Returns:
            {"success": bool, "text": str, "persona": str, "error": str}
        """
        p_config = {}
        for p in self.personas:
            if p.get("name") == persona:
                p_config = p
                break
        
        prompt = f"""Sujet : {topic}
Angle : {angle}

Génère un tweet percutant (maximum 280 caractères)."""

        system = p_config.get("system_prompt", "")
        
        result = self.generator.generate(
            prompt=prompt,
            persona=persona,
            system=system,
            max_tokens=280
        )
        
        # Asegurar que max 280 caracteres
        if result.get("success") and len(result.get("text", "")) > 280:
            result["text"] = result["text"][:277] + "..."
        
        return result
    
    def generate_thread(self, topic: str, persona: str = "thread_maker", 
                     nb_tweets: int = 5) -> Dict[str, Any]:
        """Génère un thread de tweets."""
        result = self.generate_tweet(topic, persona)
        
        if result.get("success"):
            # Ajouter des numéros de tweets
            text = result.get("text", "")
            lines = text.split("\n\n")
            
            numbered = []
            for i, line in enumerate(lines[:nb_tweets], 1):
                numbered.append(f"{i}/{nb_tweets} {line}")
            
            result["text"] = "\n\n".join(numbered)
            result["thread"] = True
        
        return result
    
    def get_personas(self) -> list:
        """Retourne les personas disponibles."""
        return self.personas


# === FONCTIONS UTILITAIRES ===

def generate_tweet(topic: str, persona: str = "hot_take", 
                account_id: int = None) -> str:
    """Génère un tweet rapidement."""
    adapter = TWAdapter(account_id)
    result = adapter.generate_tweet(topic, persona)
    return result.get("text", "")


def get_personas(account_id: int = None) -> list:
    """Liste les personas Twitter."""
    return load_personas("twitter", account_id)


if __name__ == "__main__":
    adapter = TWAdapter()
    print(f"Personas: {[p['name'] for p in adapter.get_personas()]}")