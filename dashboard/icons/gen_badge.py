"""Génère le badge icon单独的."""
import asyncio, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

ICONS_DIR = Path(__file__).resolve().parent
BADGE_HTML = ICONS_DIR / "badge.html"
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

async def main():
    await launch_chrome(9222)
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = await browser.new_page(viewport={"width": 200, "height": 200})
        await page.goto(BADGE_HTML.resolve().as_uri())
        await page.wait_for_timeout(800)
        bb = await page.evaluate("""() => {
            const svg = document.querySelector('svg');
            const w = parseFloat(svg.getAttribute('width') || '0');
            const h = parseFloat(svg.getAttribute('height') || '0');
            return { x: 0, y: 0, width: w, height: h };
        }""")
        if bb:
            await page.screenshot(
                path=str(ICONS_DIR / "icon-badge.png"),
                clip={"x": bb["x"], "y": bb["y"], "width": bb["width"], "height": bb["height"]},
            )
            print(f"[OK] icon-badge.png ({bb['width']:.0f}x{bb['height']:.0f})")
        await page.close()
        await browser.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        try: sys.stdout.reconfigure(encoding="utf-8")
        except: pass
    asyncio.run(main())