import os
import time
import requests
from typing import Optional

CANVA_API_BASE = "https://api.canva.com/rest/v1"

class CanvaClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
    
    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def get_template_fields(self, brand_template_id: str) -> dict:
        """Récupère les champs autofill du template"""
        resp = requests.get(
            f"{CANVA_API_BASE}/brand-templates/{brand_template_id}/dataset",
            headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()
    
    def create_autofill_job(self, brand_template_id: str, data: dict, title: str) -> str:
        """Crée un job autofill - retourne le job_id"""
        resp = requests.post(
            f"{CANVA_API_BASE}/autofills",
            headers=self._headers(),
            json={
                "brand_template_id": brand_template_id,
                "title": title,
                "data": data
            }
        )
        resp.raise_for_status()
        return resp.json()["job"]["id"]
    
    def wait_for_job(self, job_id: str, max_wait: int = 60) -> Optional[dict]:
        """Attend que le job soit terminé et retourne le design"""
        for _ in range(max_wait):
            resp = requests.get(
                f"{CANVA_API_BASE}/autofills/{job_id}",
                headers=self._headers()
            )
            resp.raise_for_status()
            job = resp.json()["job"]
            
            if job["status"] == "success":
                return job["result"]["design"]
            elif job["status"] == "failed":
                raise Exception(f"Job failed: {job['error']}")
            
            time.sleep(2)
        
        raise TimeoutError("Job timed out")
    
    def export_design(self, design_id: str, format: str = "png", 
                      width: int = 1080, height: int = 1080) -> str:
        """Lance l'export et retourne l'URL de téléchargement"""
        resp = requests.post(
            f"{CANVA_API_BASE}/exports",
            headers=self._headers(),
            json={
                "design_id": design_id,
                "format": {
                    "type": format,
                    "width": width,
                    "height": height
                }
            }
        )
        resp.raise_for_status()
        return resp.json()["job"]["id"]
    
    def wait_for_export(self, job_id: str, max_wait: int = 60) -> str:
        """Attend l'export et retourne l'URL de téléchargement"""
        for _ in range(max_wait):
            resp = requests.get(
                f"{CANVA_API_BASE}/exports/{job_id}",
                headers=self._headers()
            )
            resp.raise_for_status()
            job = resp.json()["job"]
            
            if job["status"] == "success":
                return job["urls"][0]
            elif job["status"] == "failed":
                raise Exception(f"Export failed")
            
            time.sleep(2)
        
        raise TimeoutError("Export timed out")


def generate_slide(template_id: str, access_token: str, 
                   slide_data: dict, title: str,
                   output_format: str = "png") -> str:
    """Génère une slide depuis un template Canva"""
    client = CanvaClient(access_token)
    
    data = {}
    for key, value in slide_data.items():
        if isinstance(value, str) and (value.startswith("http") or value.startswith("/")):
            # C'est une image - upload d'abord puis utiliser asset_id
            data[key] = {"type": "text", "text": value}
        else:
            data[key] = {"type": "text", "text": str(value)}
    
    job_id = client.create_autofill_job(template_id, data, title)
    design = client.wait_for_job(job_id)
    
    export_job_id = client.export_design(design["id"], output_format)
    download_url = client.wait_for_export(export_job_id)
    
    return download_url


# Exemple d'utilisation pour LinkedIn
if __name__ == "__main__":
    TEMPLATE_ID = "ton_brand_template_id"
    ACCESS_TOKEN = os.environ.get("CANVA_ACCESS_TOKEN")
    
    slide_data = {
        "title": "5 conseils pour réussir",
        "point1": "1. Définissez vos objectifs",
        "point2": "2. Connaissez votre audience",
        "point3": "3. Créez du contenu de valeur",
        "point4": "4. Mesurez vos résultats",
        "point5": "5. Itérez et améliorez",
        "cta": "Contactez-nous pour en savoir plus"
    }
    
    url = generate_slide(TEMPLATE_ID, ACCESS_TOKEN, slide_data, "Slide LinkedIn")
    print(f"Slide générée: {url}")