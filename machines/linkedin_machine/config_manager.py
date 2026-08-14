# config_manager.py — Centralisation de la configuration et des clés API
# Toutes les clés API sont lues depuis les variables d'environnement (fichier .env)

import os
from dotenv import load_dotenv

# Chargement du fichier .env
load_dotenv()

# --- Configuration Globlale ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
LINKEDIN_TOKEN = os.getenv("LINKEDIN_TOKEN", "")
LINKEDIN_USER_ID = os.getenv("LINKEDIN_USER_ID", "")

# Make.com Webhook
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "")

# Google Sheets
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# Modèle Groq
GROQ_MODEL = os.getenv("LINKEDIN_LLM_MODEL", "llama-3.3-70b-versatile")

def validate_config():
    """
    Vérifie que les clés essentielles sont présentes.
    """
    missing = []
    if not GROQ_API_KEY: missing.append("GROQ_API_KEY")
    
    if missing:
        print(f"⚠️ Clés manquantes dans le .env : {', '.join(missing)}")
        return False
    return True

