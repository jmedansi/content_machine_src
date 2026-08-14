import json
import os
import subprocess
import time
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

REMOTION_DIR = Path("D:/Content_Machine/machines/linkedin-machine/remotion-engine")
OUTPUT_DIR = REMOTION_DIR / "output"

class RemotionExporter:
    def __init__(self, port: int = 8777):
        self.port = port
        self.server_process = None
        
    def start_preview_server(self):
        """Démarre le serveur preview Remotion"""
        self.server_process = subprocess.Popen(
            ["npx", "remotion", "preview", "src/index.ts", "--port", str(self.port)],
            cwd=str(REMOTION_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        time.sleep(5)
        print(f"✅ Serveur Remotion démarré sur http://localhost:{self.port}")
        
    def stop_preview_server(self):
        """Arrête le serveur"""
        if self.server_process:
            self.server_process.terminate()
            self.server_process.wait()
            
    async def capture_slide(
        self,
        props: dict,
        composition: str = "Carousel",
        output_file: str = "slide.png",
        frame: int = 15,
        scale: float = 2.0
    ) -> str:
        """
        Capture une slide en haute qualité via Playwright
        
        Args:
            props: Propriétés du slide (titre, sous-titre, etc.)
            composition: Nom de la composition Remotion
            output_file: Nom du fichier de sortie
            frame: Frame à capturer
            scale: Échelle de capture (2.0 = 2x, 3.0 = 3x pour haute qualité)
        
        Returns:
            Chemin du fichier PNG généré
        """
        props_file = REMOTION_DIR / "capture_props.json"
        with open(props_file, "w", encoding="utf-8") as f:
            json.dump(props, f)
        
        url = f"http://localhost:{self.port}/~preview?composition={composition}&propsFile=capture_props.json&frame={frame}"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=scale
            )
            
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(2000)
            
            output_path = REMOTION_DIR / output_file
            await page.screenshot(
                path=str(output_path),
                full_page=False,
                type="png"
            )
            
            await browser.close()
            
        print(f"📸 Slide capturée: {output_path}")
        return str(output_path)
    
    async def capture_carousel(
        self,
        slides: list,
        output_dir: str = None
    ) -> list:
        """
        Capture toutes les slides d'un carousel
        
        Args:
            slides: Liste des props pour chaque slide
            output_dir: Répertoire de sortie
        
        Returns:
            Liste des chemins d'images générées
        """
        if output_dir:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        results = []
        
        for i, slide_props in enumerate(slides):
            output_file = f"slide_{i+1:02d}.png"
            
            file_path = await self.capture_slide(
                props={"slides": [slide_props]},
                output_file=output_file,
                frame=15
            )
            results.append(file_path)
            
        return results


async def export_high_quality_slide(
    title: str,
    subtitle: str = None,
    visual_type: str = "intro",
    output: str = "linkedin_slide.png"
) -> str:
    """
    Exporte une slide LinkedIn en haute qualité (PNG 2x)
    
    Usage:
        image_path = await export_high_quality_slide(
            title="5 conseils pour réussir",
            subtitle="Stratégie B2B",
            visual_type="intro",
            output="ma_slide.png"
        )
    """
    props = {
        "slides": [{
            "text": f"{title}:{subtitle}" if subtitle else title,
            "visualType": visual_type,
            "durationInFrames": 30
        }]
    }
    
    exporter = RemotionExporter()
    exporter.start_preview_server()
    
    try:
        image_path = await exporter.capture_slide(
            props=props,
            output_file=output,
            scale=2.0
        )
    finally:
        exporter.stop_preview_server()
    
    return image_path


async def export_linkedin_carousel(
    slides_content: list,
    output_prefix: str = "carousel"
) -> list:
    """
    Exporte un carousel LinkedIn complet
    
    Args:
        slides_content: Liste de tuples (title, subtitle)
        output_prefix: Préfixe des fichiers
    
    Returns:
        Liste des chemins d'images
    """
    slides = []
    for i, (title, subtitle) in enumerate(slides_content):
        visual_type = "intro" if i == 0 else ("step" if i < len(slides_content) - 1 else "cta")
        
        slides.append({
            "text": f"{title}:{subtitle}" if subtitle else title,
            "visualType": visual_type,
            "durationInFrames": 30,
            "index": i,
            "totalSlides": len(slides_content)
        })
    
    exporter = RemotionExporter()
    exporter.start_preview_server()
    
    try:
        results = await exporter.capture_carousel(slides)
    finally:
        exporter.stop_preview_server()
    
    return results


if __name__ == "__main__":
    async def main():
        print("=> Export haute qualite Remotion -> PNG")
        
        result = await export_high_quality_slide(
            title="L'IA au service",
            subtitle="de votre croissance B2B",
            output="incidenx_slide.png"
        )
        
        print(f"=> Genere: {result}")
        
    asyncio.run(main())