# google_sheets_utils.py — Utilitaire pour l'intégration Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
import config_manager

# Configuration du logging
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

def get_sheet():
    """
    Initialise la connexion à Google Sheets et retourne l'objet sheet.
    """
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(config_manager.GOOGLE_SERVICE_ACCOUNT_JSON, scope)
        client = gspread.authorize(creds)
        
        if not config_manager.GOOGLE_SHEET_ID:
            return None
            
        sheet = client.open_by_key(config_manager.GOOGLE_SHEET_ID)
        return sheet
    except Exception as e:
        logging.error(f"Erreur de connexion Google Sheets : {e}")
        return None

def log_to_sheet(worksheet_name, data):
    """
    Ajoute une ligne de données à une feuille spécifique.
    data doit être une liste.
    """
    sheet = get_sheet()
    if not sheet:
        return False
    
    try:
        try:
            worksheet = sheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # Créer la feuille si elle n'existe pas
            worksheet = sheet.add_worksheet(title=worksheet_name, rows="100", cols="20")
            # Optionnel: ajouter des en-têtes ici si data est un dict
        
        worksheet.append_row(data)
        return True
    except Exception as e:
        logging.error(f"Erreur d'écriture dans Google Sheets ({worksheet_name}) : {e}")
        return False
