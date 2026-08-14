import os
import asyncio
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

class CarouselRenderer:
    def __init__(self, templates_dir='templates'):
        """Initialise le moteur de rendu HTML/Image."""
        self.templates_dir = os.path.abspath(templates_dir)
        # Prépare l'environnement Jinja2
        self.env = Environment(loader=FileSystemLoader(self.templates_dir))
        
    async def render_slide(self, slide_data, output_path, total_slides):
        """Prend les données d'une slide, injecte dans l'HTML et prend une capture d'écran."""
        index = slide_data.get('index', 0)
        is_intro = slide_data.get('visualType', '') == 'intro' or index == 1
        texte_complet = slide_data.get('text', '')
        
        # Parse le texte (Titre : Sous-titre)
        titre = texte_complet
        texte = ""
        if ":" in texte_complet:
            parts = texte_complet.split(":", 1)
            titre = parts[0].strip()
            texte = parts[1].strip()
            
        # Format du Titre (Hook) pour l'intro (Mettre le premier mot en bleu)
        titre_hook = titre
        if is_intro:
            mots = titre.split()
            if len(mots) > 0:
                mots[0] = f"<span class='highlight'>{mots[0]}</span>"
                titre_hook = " ".join(mots)
                
        # Calcul de la jauge de progression
        progress = (index / total_slides) * 100

        # Données envoyées au template HTML
        context = {
            'is_intro': is_intro,
            'index': index,
            'progress': progress,
            'titre_hook': titre_hook,
            'titre': titre,
            'texte': texte,
            'image_url': slide_data.get('imagePath', None) # Pour la future intégration Gemini
        }

        # 1. Rendu HTML en mémoire via Jinja2
        template = self.env.get_template('slide_template.html')
        html_content = template.render(**context)

        # 2. Capture d'écran via Playwright
        async with async_playwright() as p:
            # Lancement du navigateur invisible
            browser = await p.chromium.launch(headless=True)
            
            # Paramétrage de la qualité : "Retina" (device_scale_factor=3)
            # Une slide de 1080x1080 sera ainsi générée en 3240x3240 très haute netteté.
            context = await browser.new_context(
                viewport={"width": 1080, "height": 1080},
                device_scale_factor=3
            )
            page = await context.new_page()
            
            # Chargement du code HTML généré
            await page.set_content(html_content, wait_until='networkidle')
            
            # Sauvegarde de l'image
            await page.screenshot(path=output_path)
            await browser.close()
            
        logging.info(f"✅ Slide {index}/{total_slides} générée : {os.path.basename(output_path)}")

    def build_carousel_images_sync(self, slides, output_dir):
        """Méthode synchrone pour générer toutes les slides (facilite l'appel depuis generate_carousel.py)."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        images_paths = []
        total_slides = len(slides)
        
        async def render_all():
            for i, slide in enumerate(slides):
                # Ajouter l'index 1-based aux données
                slide['index'] = i + 1
                nom_fichier = f"slide_{i+1:02d}.png"
                output_path = os.path.join(output_dir, nom_fichier)
                
                await self.render_slide(slide, output_path, total_slides)
                images_paths.append(output_path)
                
        # Exécute la boucle asynchrone playwight
        asyncio.run(render_all())
        return images_paths

# Test unitaire rapide si le script est lancé seul
if __name__ == "__main__":
    test_slides = [
        {"text": "L'AUTOMATISATION : Transformez votre PME", "visualType": "intro"},
        {"text": "LE PROBLÈME : Vous perdez 15h par semaine sur des tâches répétitives.", "visualType": "step"},
        {"text": "LE TEST IMAGE : Voici comment Gemini va s'intégrer ICI.", "visualType": "step", "imagePath": "https://picsum.photos/600/300"},
        {"text": "LA SOLUTION : Envoyez 'MACHINE' en DM.", "visualType": "cta"}
    ]
    
    renderer = CarouselRenderer()
    print("🚀 Lancement du test unitaire de rendu HTML -> PNG...")
    paths = renderer.build_carousel_images_sync(test_slides, output_dir="test_html_output")
    print(f"✅ Terminé ! {len(paths)} images générées dans /test_html_output")
