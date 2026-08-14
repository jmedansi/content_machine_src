import os
import json
import subprocess
import time
from pathlib import Path
from agents.carousel_writer import generate_carousel_content
import img2pdf

# Paths
BASE_DIR = Path(__file__).parent
ENGINE_DIR = BASE_DIR / "remotion-engine"
CONTENT_DIR = BASE_DIR / "content" / "carousels"
TEMP_DIR = BASE_DIR / "temp"

def generate_linkedin_carousel(topic):
    """Génère le carousel LinkedIn complet (Texte -> Images -> Remotion -> PDF)."""
    print(f"🚀 Lancement de la génération pour le sujet : {topic}")
    
    # 1. Génération du contenu rédactionnel
    print("[INFO] Rédaction des 7 slides via LLM...")
    content = generate_carousel_content(topic)
    if not content:
        print("[ERROR] Échec de la rédaction (Ollama et Groq ont échoué).")
        return
    
    # Préparer le dossier de sortie
    timestamp = int(time.time())
    carousel_id = f"carousel_{timestamp}"
    output_dir = CONTENT_DIR / carousel_id
    output_dir.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)
    
    # 2. Rendu des slides via Moteur HTML (Python)
    print(f"[INFO] Rendu des {len(content['slides'])} slides via Playwright...")
    
    from html_renderer import CarouselRenderer
    renderer = CarouselRenderer(templates_dir=BASE_DIR / "templates")
    image_paths = renderer.build_carousel_images_sync(content["slides"], output_dir=output_dir)
    
    # 3. Assemblage en PDF
    if image_paths:
        pdf_path = output_dir / f"{carousel_id}.pdf"
        print(f"[INFO] Assemblage du PDF final ({len(image_paths)} slides)...")
        
        try:
            with open(pdf_path, "wb") as f:
                f.write(img2pdf.convert(image_paths))
            
            print(f"\n✅ SUCCESS! Carousel généré dans : {output_dir}")
            print(f"📍 PDF : {pdf_path}")
        except Exception as e:
            print(f"❌ Erreur lors de l'assemblage PDF : {e}")
    else:
        print("[ERROR] Aucun slide n'a été rendu. Le PDF ne peut pas être généré.")

if __name__ == "__main__":
    import sys
    default_topic = "Les secrets de l'IA pour gagner 2h par jour"
    if len(sys.argv) > 1:
        default_topic = sys.argv[1]
    
    generate_linkedin_carousel(default_topic)
