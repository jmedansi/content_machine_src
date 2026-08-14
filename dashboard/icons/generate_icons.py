"""
Génère des PNG pour les icônes PWA.
Charge chaque SVG individuel et capture à la taille exacte.
"""
import asyncio, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

ICONS_DIR = Path(__file__).resolve().parent
HTML_FILE = ICONS_DIR / "logo_design.html"
CHROME_USER_DATA = os.path.expandvars("%LOCALAPPDATA%/Google/Chrome/User Data")
CHROME_PROFILE = os.path.join(CHROME_USER_DATA, "Profile 1")

def is_port_open(port, host="localhost"):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

async def launch_chrome(pport=9222):
    import subprocess
    if is_port_open(pport):
        return True
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(chrome_path):
        chrome_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    subprocess.Popen([
        chrome_path, f"--remote-debugging-port={pport}",
        f"--user-data-dir={CHROME_PROFILE}", "https://gemini.google.com"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(2)
    return True

async def capture(browser, svg_id, filename, w, h):
    page = await browser.new_page(viewport={"width": w, "height": h})
    await page.goto(HTML_FILE.resolve().as_uri())
    await page.wait_for_timeout(600)

    loc = page.locator(f"#{svg_id}")
    bb = await loc.bounding_box()
    if bb and bb["width"] > 0 and bb["height"] > 0:
        await page.screenshot(
            path=str(ICONS_DIR / filename),
            clip={"x": bb["x"], "y": bb["y"], "width": bb["width"], "height": bb["height"]},
        )
    else:
        await page.screenshot(path=str(ICONS_DIR / filename), full_page=False)
    await page.close()

async def generate():
    await launch_chrome(9222)
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")

        for filename, w, h in [
            ("icon-512.png", 512, 512),
            ("icon-384.png", 384, 384),
            ("icon-192.png", 192, 192),
            ("icon-144.png", 144, 144),
            ("icon-128.png", 128, 128),
            ("icon-96.png", 96, 96),
            ("icon-72.png", 72, 72),
        ]:
            await capture(browser, "logo-full", filename, w, h)
            print(f"[OK] {filename}")
            print(f"[OK] {filename} ({w}x{h})")

        await capture(browser, "logo-badge", "icon-badge.png", 192, 192)
        print(f"[OK] icon-badge.png (192x192 badge)")

        await browser.close()

    print("\nFichiers générés:", [f.name for f in ICONS_DIR.glob("icon*.png")])

if __name__ == "__main__":
    if sys.platform == "win32":
        try: sys.stdout.reconfigure(encoding="utf-8")
        except: pass
    asyncio.run(generate())