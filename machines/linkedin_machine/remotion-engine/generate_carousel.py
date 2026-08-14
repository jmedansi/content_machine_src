import asyncio
import json
import os
from playwright.async_api import async_playwright

async def generate_carousel(slides: list, output_dir: str = "output"):
    """Génère un carousel LinkedIn complet"""
    os.makedirs(output_dir, exist_ok=True)
    
    results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        for i, slide in enumerate(slides):
            props = {"slides": [{**slide, "index": i, "totalSlides": len(slides)}]}
            
            with open("temp_props.json", "w", encoding="utf-8") as f:
                json.dump(props, f)
            
            url = f"http://localhost:8877/~preview?composition=Carousel&propsFile=temp_props.json&frame=15"
            
            page = await browser.new_page(viewport={"width": 1080, "height": 1080}, device_scale_factor=2)
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            
            output_file = f"{output_dir}/slide_{i+1:02d}.png"
            await page.screenshot(path=output_file, full_page=False, type="png")
            await page.close()
            
            size = os.path.getsize(output_file)
            print(f"Slide {i+1}: {size} octets")
            results.append(output_file)
        
        await browser.close()
    
    return results


if __name__ == "__main__":
    slides = [
        {"text": "5 conseils stratégiques:pour transformer votre business B2B", "visualType": "intro"},
        {"text": "1. Définissez votre ICP:Ideal Customer Profile clair", "visualType": "step"},
        {"text": "2. Créez votre funnel:de leads qualifiés", "visualType": "step"},
        {"text": "3. Automatisez le suivi:votre machine à deals", "visualType": "step"},
        {"text": "4. Mesurez et optimisez:votre ROI en continu", "visualType": "step"},
        {"text": "Prêt à passer au niveau supérieur ?:Envoyez MACHINE en DM", "visualType": "cta"}
    ]
    
    results = asyncio.run(generate_carousel(slides))
    print(f"\n{len(results)} slides générées")