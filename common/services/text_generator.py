# text_generator.py — Moteur de génération de texte commun
# Usage: from common.services.text_generator import TextGenerator, generate_text

import os
import sys
import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TextGenerator:
    """Moteur de génération de texte via Groq - partagé entre toutes les plateformes."""
    
    def __init__(self, platform: str = "facebook"):
        self.platform = platform
        self._load_personas()
    
    def _load_personas(self):
        """Charge les personas disponibles pour cette plateforme."""
        from common.utils.persona_loader import load_personas
        self.personas = load_personas(self.platform)
        logger.info(f"[TextGenerator] {len(self.personas)} personas loaded for {self.platform}")
    
    def _clean_reasoning(self, text: str) -> str:
        """Supprime les balises de reasoning."""
        patterns = [
            r'<think[^>]*>.*?</think[^>]*>',
            r'<thinking[^>]*>.*?</thinking[^>]*>',
            r'<reasoning[^>]*>.*?</reasoning[^>]*>',
            r'<think>.*?</think>',
        ]
        for p in patterns:
            text = re.sub(p, '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'\n\s*\n', '\n', text)
        text = re.sub(r' +', ' ', text).strip()
        return text
    
    def generate(self, prompt: str, persona: str = None, system: str = None, 
                model: str = "llama-3.3-70b-versatile", 
                max_tokens: int = 1000, temperature: float = 0.7) -> Dict[str, Any]:
        """
        Génère du texte via Groq.
        
        Args:
            prompt: Le prompt utilisateur
            persona: Nom du persona (optionnel - cherchera dans les personas loaded)
            system: System prompt (optionnel - sera construit depuis persona si non fourni)
            model: Modèle Groq à utiliser
            max_tokens: Limite de tokens
            temperature: Température de génération
        
        Returns:
            {"success": bool, "text": str, "persona": str, "error": str}
        """
        from common.services.api_client import api_client
        
        final_system = system
        config = {}
        
        # Si persona spécifié, charger ses paramètres
        if persona and self.personas:
            for p in self.personas:
                if p.get("name") == persona:
                    config = p.get("config", {})
                    if not final_system:
                        final_system = p.get("system_prompt", "")
                    break
        
        try:
            # Appel API
            result = api_client.call_groq(
                prompt=prompt,
                system=final_system or "Tu es un assistant expert.",
                model=model,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            if not result:
                return {"success": False, "text": "", "persona": persona, "error": "API call failed"}
            
            # Nettoyer le reasoning
            cleaned = self._clean_reasoning(result)
            
            return {"success": True, "text": cleaned, "persona": persona}
        
        except Exception as e:
            logger.error(f"[TextGenerator] Error: {e}")
            return {"success": False, "text": "", "persona": persona, "error": str(e)}
    
    def get_personas(self) -> list:
        """Retourne la liste des personas disponibles."""
        return self.personas


# === FONCTIONS UTILITAIRES ===

def generate_text(prompt: str, platform: str = "facebook", persona: str = None, 
                model: str = "llama-3.3-70b-versatile") -> str:
    """
    Fonction utilitaire simple pour générer du texte.
    
    Usage:
        text = generate_text("Écris un post sur...", platform="linkedin", persona="b2b_expert")
    """
    generator = TextGenerator(platform=platform)
    result = generator.generate(prompt, persona=persona, model=model)
    
    if result.get("success"):
        return result.get("text", "")
    return ""


def get_available_personas(platform: str) -> list:
    """Retourne les personas disponibles pour une plateforme."""
    generator = TextGenerator(platform=platform)
    return generator.get_personas()