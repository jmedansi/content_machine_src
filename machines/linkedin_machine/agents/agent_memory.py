# agent_memory.py — Gestion de l'anti-répétition et journalisation
import sys
import io
import json
import logging
from pathlib import Path
from datetime import datetime

# Forcer l'encodage UTF-8 pour le terminal Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from agents.google_sheets_utils import log_to_sheet

MEMORY_PATH = Path("data/memory.json")

# Configuration du logging
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

def log_published(topic, linkedin_url=""):
    """
    Enregistre un sujet publié dans memory.json et dans Google Sheets.
    """
    try:
        # Journalisation locale (JSON)
        memory = []
        if MEMORY_PATH.exists():
            try:
                memory = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                memory = []
        
        entry = {
            "titre": topic["titre"],
            "secteur": topic.get("secteur", "N/A"),
            "date_publiee": datetime.now().isoformat(),
            "linkedin_url": linkedin_url
        }
        
        memory.append(entry)
        MEMORY_PATH.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ Mémorisé localement : {topic['titre']}")
        
        # Journalisation Cloud (Google Sheets)
        # On définit les colonnes : Date, Titre, Secteur, URL
        sheet_data = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            topic["titre"],
            topic.get("secteur", "N/A"),
            linkedin_url
        ]
        if log_to_sheet("Publications", sheet_data):
            print(f"✅ Mémorisé dans Google Sheets : {topic['titre']}")
        else:
            print(f"⚠️ Échec de la mémorisation dans Google Sheets (vérifiez errors.log)")

    except Exception as e:
        logging.error(f"Erreur dans agent_memory.py : {e}")
        print(f"❌ Erreur lors de la mémorisation : {e}")
