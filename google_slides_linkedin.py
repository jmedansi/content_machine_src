import os
import io
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = [
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file'
]

class GoogleSlidesClient:
    def __init__(self, credentials_path: str):
        self.credentials = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=SCOPES
        )
        self.slides_service = build('slides', 'v1', credentials=self.credentials)
        self.drive_service = build('drive', 'v3', credentials=self.credentials)
    
    def create_presentation(self, title: str) -> str:
        """Crée une nouvelle présentation"""
        presentation = self.slides_service.presentations().create(
            body={'title': title}
        ).execute()
        return presentation['presentationId']
    
    def copy_template(self, template_id: str, title: str) -> str:
        """Copie un template existant"""
        body = {
            'name': title,
            'parents': []  # Root folder
        }
        copied = self.drive_service.files().copy(
            fileId=template_id, body=body
        ).execute()
        return copied['id']
    
    def get_template_fields(self, presentation_id: str) -> list:
        """Récupère les placeholders du template"""
        presentation = self.slides_service.presentations().get(
            presentationId=presentation_id
        ).execute()
        
        fields = []
        for slide in presentation.get('slides', []):
            for element in slide.get('pageElements', []):
                if 'shape' in element:
                    shape = element['shape']
                    if shape.get('text', {}).get('text', {}).get('content'):
                        text = shape['text']['text']['content'].strip()
                        if text.startswith('{{') and text.endswith('}}'):
                            fields.append({
                                'id': element['objectId'],
                                'placeholder': text[2:-2]
                            })
        return fields
    
    def replace_text(self, presentation_id: str, replacements: dict):
        """Remplace les placeholders par du texte"""
        requests = []
        
        for placeholder, value in replacements.items():
            requests.append({
                'replaceAllText': {
                    'containsText': {
                        'text': f'{{{{{placeholder}}}}}',
                        'matchCase': False
                    },
                    'replaceText': value
                }
            })
        
        if requests:
            self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': requests}
            ).execute()
    
    def replace_image(self, presentation_id: str, placeholder_id: str, image_url: str):
        """Remplace un placeholder par une image"""
        import requests as req
        
        resp = req.get(image_url)
        image_data = resp.content
        
        requests = [{
            'createImage': {
                'element': {
                    'objectId': placeholder_id + '_img',
                    'size': {
                        'width': {'magnitude': 400, 'unit': 'PT'},
                        'height': {'magnitude': 300, 'unit': 'PT'}
                    },
                    'transform': {
                        'scaleX': 1,
                        'scaleY': 1,
                        'translateX': 0,
                        'translateY': 0,
                        'unit': 'PT'
                    }
                },
                'url': image_url
            }
        }]
        
        self.slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()
    
    def export_to_png(self, presentation_id: str, slide_index: int = 0) -> bytes:
        """Exporte une slide en PNG"""
        # Export as PDF first
        from googleapiclient.http import MediaIoBaseDownload
        
        # Use Drive API to export
        export_mime = 'application/pdf'
        request = self.drive_service.files().export_media(
            fileId=presentation_id,
            mimeType=export_mime
        )
        
        pdf_file = io.BytesIO()
        downloader = MediaIoBaseDownload(pdf_file, request)
        done = False
        
        while not done:
            _, done = downloader.next_chunk()
        
        return pdf_file.getvalue()
    
    def download_thumbnail(self, presentation_id: str, slide_index: int = 0) -> bytes:
        """Récupère le thumbnail d'une slide"""
        # Generate thumbnail via slides API
        presentation = self.slides_service.presentations().get(
            presentationId=presentation_id
        ).execute()
        
        slides = presentation.get('slides', [])
        if slide_index >= len(slides):
            raise ValueError(f"Slide index {slide_index} out of range")
        
        slide_id = slides[slide_index]['objectId']
        
        # Get thumbnail via page
        page = self.slides_service.presentations().pages().getThumbnail(
            presentationId=presentation_id,
            pageObjectId=slide_id
        ).execute()
        
        # Download the thumbnail URL
        import requests as req
        resp = req.get(page['contentUrl'])
        return resp.content


def generate_slide_from_template(
    credentials_path: str,
    template_id: str,
    slide_data: dict,
    title: str
) -> bytes:
    """
    Génère une slide LinkedIn depuis un template Google Slides
    
    Args:
        credentials_path: Chemin vers le fichier JSON du service account
        template_id: ID du template Google Slides (depuis l'URL)
        slide_data: Dict avec les valeurs à injector
        title: Titre de la présentation
    
    Returns:
        Bytes de l'image PNG
    """
    client = GoogleSlidesClient(credentials_path)
    
    # Copier le template
    presentation_id = client.copy_template(template_id, title)
    
    # Remplacer le texte
    text_data = {k: v for k, v in slide_data.items() if isinstance(v, str)}
    client.replace_text(presentation_id, text_data)
    
    # Remplacer les images (si nécessaire)
    for key, value in slide_data.items():
        if key.startswith('image_') and isinstance(value, str):
            pass  # À implémenter selon le placeholder
    
    # Exporter en image
    thumbnail = client.download_thumbnail(presentation_id)
    
    # Nettoyer (supprimer la présentation créée)
    client.drive_service.files().delete(fileId=presentation_id).execute()
    
    return thumbnail


# === EXAMPLE D'UTILISATION ===

if __name__ == "__main__":
    CREDENTIALS = "path/to/your/credentials.json"
    TEMPLATE_ID = "1abc123def456..."  # ID depuis l'URL du template
    
    slide_data = {
        "title": "5 conseils pour réussir",
        "subtitle": "Stratégie digitale 2024",
        "point1": "1. Définissez vos objectifs",
        "point2": "2. Connaissez votre audience",
        "point3": "3. Créez du contenu de valeur",
        "point4": "4. Mesurez vos résultats",
        "point5": "5. Itérez et améliorez",
        "cta": "Contactez-nous pour en savoir plus"
    }
    
    client = GoogleSlidesClient(CREDENTIALS)
    
    # Créer depuis le template
    pres_id = client.copy_template(TEMPLATE_ID, "Slide LinkedIn")
    client.replace_text(pres_id, slide_data)
    
    # Exporter
    image_bytes = client.download_thumbnail(pres_id)
    
    # Sauvegarder
    with open("slide_linkedin.png", "wb") as f:
        f.write(image_bytes)
    
    print("Slide générée: slide_linkedin.png")