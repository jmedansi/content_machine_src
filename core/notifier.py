import requests
import logging
from core.config import Config

logger = logging.getLogger("notifier")

def send_telegram_message(message: str):
    """Envoie un message Telegram à l'utilisateur."""
    token = Config.TELEGRAM_TOKEN
    chat_id = Config.TELEGRAM_CHAT_ID
    
    if not token or not chat_id:
        logger.warning("Telegram non configuré (TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant)")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Erreur envoi Telegram: {e}")
        return False

def notify_batch_completed(success_count: int, total_count: int):
    """Notifie la fin de la génération d'un batch."""
    msg = (
        "🤖 *Facebook Machine - Batch Terminé*\n\n"
        f"✅ {success_count}/{total_count} posts ont été générés avec succès.\n"
        "👉 Connectez-vous au Dashboard pour les valider avant publication.\n\n"
        "🔗 http://localhost:8001"
    )
    return send_telegram_message(msg)
