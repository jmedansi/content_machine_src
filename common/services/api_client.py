# api_client.py — Client API commun pour toutes les plateformes
# Usage: from common.services.api_client import APIClient

import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class APIClient:
    """Client HTTP commun pour les appels API (Groq, Gemini, etc.)."""
    
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_api_key_2 = os.getenv("GROQ_API_KEY_2", "")
        self.groq_api_keys = self._load_groq_keys()
        self.current_key_index = 0
    
    def _load_groq_keys(self):
        """Charge toutes les clés Groq depuis l'environnement."""
        keys = []
        for i in range(1, 10):
            key = os.getenv(f"GROQ_API_KEY_{i}")
            if key:
                keys.append(key)
        if not keys and self.groq_api_key:
            keys = [self.groq_api_key]
        return keys
    
    def get_groq_key(self) -> str:
        """Retourne la clé Groq actuelle (rotation automatique)."""
        if not self.groq_api_keys:
            raise Exception("Aucune clé Groq disponible")
        key = self.groq_api_keys[self.current_key_index]
        return key
    
    def rotate_groq_key(self):
        """Passe à la clé suivante (en cas d'erreur 429)."""
        if len(self.groq_api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.groq_api_keys)
            logger.info(f"[APIClient] Rotation vers clé #{self.current_key_index}")
        else:
            logger.warning("[APIClient] Une seule clé disponible, pas de rotation")
    
    def call_groq(self, prompt: str, system: str = None, model: str = "llama-3.3-70b-versatile", 
                max_tokens: int = 1000, temperature: float = 0.7) -> Optional[str]:
        """Appel Groq avec rotation automatique des clés."""
        import requests
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        for attempt in range(len(self.groq_api_keys)):
            try:
                api_key = self.get_groq_key()
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
                    timeout=60
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                elif response.status_code == 429:
                    logger.warning(f"[APIClient] 429 sur clé #{self.current_key_index}, rotation...")
                    self.rotate_groq_key()
                else:
                    logger.error(f"[APIClient] Erreur Groq {response.status_code}: {response.text[:200]}")
                    return None
            except Exception as e:
                logger.error(f"[APIClient] Exception: {e}")
                return None
        
        logger.error("[APIClient] Toutes les clés Groq épuisées")
        return None


# Instance globale partagée
api_client = APIClient()