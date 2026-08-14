import asyncio
import os
import time
import base64
import subprocess
import socket
import sys
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
import requests

# Chemins relatifs à ce dossier agent
_AGENT_DIR = Path(__file__).resolve().parent

# Import du module de nettoyage de filigrane (co-localisé dans ce dossier)
try:
    sys.path.insert(0, str(_AGENT_DIR))
    from watermark_eraser_tool import erase_gemini_watermark
except ImportError:
    def erase_gemini_watermark(p): pass

# Fix encoding for Windows consoles (to handle emojis and accents)
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# ===== CONFIGURATION =====
GEMINI_URL = "https://gemini.google.com/app"
PROMPT_FILE = _AGENT_DIR / "image_prompt.txt"
TEMP_DIR = _AGENT_DIR / "temp"
DOWNLOADS_DIR = Path(os.path.expanduser("~/Downloads"))
try:
    from core.paths import GITHUB_REPO, GITHUB_BRANCH, CHROME_DEBUG_PORT
except ImportError:
    GITHUB_REPO = os.getenv("GITHUB_REPO", "jmedansi/temp")
    GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
    CHROME_DEBUG_PORT = int(os.getenv("CHROME_DEBUG_PORT", "9222"))
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents"
RAW_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"

def is_port_open(port, host='localhost'):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

def launch_chrome():
    if is_port_open(CHROME_DEBUG_PORT):
        print(f"[INFO] Chrome already running on port {CHROME_DEBUG_PORT}")
        return True

    print(f"[INFO] Launching Chrome on port {CHROME_DEBUG_PORT}...")
    chrome_paths = [
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        os.path.expandvars("%LOCALAPPDATA%/Google/Chrome/Application/chrome.exe"),
    ]
    chrome_path = next((p for p in chrome_paths if os.path.exists(p)), "chrome")
    CHROME_USER_DATA = os.path.expandvars("%LOCALAPPDATA%/Google/Chrome/User Data")
    chrome_profile_path = os.path.join(CHROME_USER_DATA, "Profile 1")
    
    subprocess.Popen([
        chrome_path,
        f"--remote-debugging-port={CHROME_DEBUG_PORT}",
        f"--user-data-dir={chrome_profile_path}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-infobars",
        "--silent-launch",
    ])
    
    for _ in range(15):
        time.sleep(1)
        if is_port_open(CHROME_DEBUG_PORT):
            print(f"[SUCCESS] Chrome launched (Silent/Clean).")
            return True
    return False

def load_token():
    token = os.getenv("GITHUB_TOKEN")
    if token: return token
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    if k.strip() == "GITHUB_TOKEN": return v.strip()
    return None

GITHUB_TOKEN = load_token()
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"} if GITHUB_TOKEN else {}

async def main():
    browser = None
    try:
        TEMP_DIR.mkdir(exist_ok=True)
        if not launch_chrome(): return

        p_path = Path(PROMPT_FILE)
        prompt = p_path.read_text(encoding="utf-8").strip() if p_path.exists() else sys.argv[1] if len(sys.argv) > 1 else "A majestic lion"
        if not prompt.lower().startswith("génère"): prompt = "Génère " + prompt
            
        print(f"[INFO] Target Prompt: {prompt[:60]}...")

        async with async_playwright() as p:
            print(f"[INFO] Connecting to Chrome...")
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0]
            
            # Force un nouvel onglet pour que chaque instance de script ait son propre espace
            page = await context.new_page()

            # Surveillance du download
            d_task = None
            def on_d(d): nonlocal d_task; d_task = d
            page.on("download", on_d)

            # --- ETAPE 1 : ACCUEIL ---
            print("[INFO] Navigating to Home...")
            await page.goto(GEMINI_URL)
            await page.wait_for_timeout(3000)

            # --- ETAPE 2 : ACTIVER LE MODE IMAGE ---
            print("[INFO] Identification du bouton 'Create image'...")
            cards = await page.query_selector_all('button.card-zero-state')
            target_card = None
            for card in cards:
                try:
                    text = await card.text_content()
                    if "image" in text.lower():
                        target_card = card; break
                except: continue
            
            if target_card:
                print(f"[INFO] Clicking Creation Card...")
                await target_card.click()
                await page.wait_for_timeout(2000)

            # --- ETAPE 3 : SAISIE DU PROMPT ---
            print("[INFO] Saisie du prompt...")
            chat_input = await page.wait_for_selector('div[aria-label*="image"], div[role="textbox"]', timeout=30000)
            await chat_input.click()
            await chat_input.fill("")
            await page.keyboard.type(prompt, delay=20)
            await page.wait_for_timeout(1000)
            
            print("[INFO] Envoi à Gemini...")
            s_btn = await page.query_selector('button[aria-label*="Send"], button[aria-label*="Envoyer"]')
            if s_btn and await s_btn.is_visible(): await s_btn.click()
            else: await page.keyboard.press("Enter")
            
            # --- ETAPE 4 : SURVEILLANCE PAR BOUTON STOP ---
            print("\n" + "="*60)
            print("[INFO] WAITING FOR 'STOP' BUTTON TO DISAPPEAR (GENERATION)...")
            print("="*60)
            
            # 1. Attendre que le bouton "Stop" apparaisse ou que le chargement commence
            await page.wait_for_timeout(5000)
            
            found_done = False
            for minute in range(1, 11):
                print(f"[POLL] Minute {minute}/10: Monitoring progress...")
                for _ in range(60):
                    # On check le bouton STOP/Interrupt
                    stop_btn = await page.query_selector('button[aria-label*="Stop"], button[aria-label*="Arrêter"], button[aria-label*="Interrupt"]')
                    
                    # On check aussi la présence de la barre de réponse finale
                    signals = await page.query_selector_all('button[aria-label*="response"], button[aria-label*="réponse"]')
                    
                    # Logique : Si pas de bouton Stop ET qu'une nouvelle réponse est arrivée (au moins une barre)
                    if (not stop_btn or not await stop_btn.is_visible()) and len(signals) > 0:
                        # On attend encore 2s pour la stabilité
                        await asyncio.sleep(2)
                        print(f"\n[SUCCESS] Signal detected! Generation seems complete at {minute}m.")
                        found_done = True; break
                    
                    await asyncio.sleep(1)
                if found_done: break

            if not found_done:
                print("\n[FAILED] Generation timeout after 10m.")
                return

            # --- ETAPE 5 : HOVER + TELECHARGEMENT (PATIENCE MAX) ---
            print("[INFO] Finalisation: Patience accrue (15 essais)...")
            await asyncio.sleep(8) # Pause plus longue pour laisser Nano Banana s'en aller

            sc_path = TEMP_DIR / f"debug_gen_{int(time.time())}.png"
            await page.screenshot(path=str(sc_path))
            print(f"[DEBUG] Final Check Screenshot: {sc_path.name}")

            success = False
            for retry in range(15): # 15 essais = ~1m30 max
                try:
                    # On RE-CHERCHE l'image à chaque essai
                    img_btn = await page.wait_for_selector('button.image-button', state="attached", timeout=6000)
                    if img_btn:
                        print(f"[INFO] Image logic attempt {retry+1}/15...")
                        await img_btn.hover(force=True)
                        await page.wait_for_timeout(3000)
                        
                        # Recherche du bouton de téléchargement
                        d_btn = await page.query_selector('button[aria-label*="Download full size"], button[aria-label*="Télécharger"]')
                        if d_btn:
                            print("[INFO] Download button found! Clicking...")
                            await d_btn.click()
                            success = True; break
                        else:
                            print("[DEBUG] Hover done but download button hidden, retrying...")
                except Exception as e:
                    print(f"[DEBUG] DOM Still Loading ({e}), retry {retry+1}/15...")
                
                await asyncio.sleep(3)

            if not success:
                print("[ERROR] Final hover/download interaction failed after 15 retries.")
                return

            # --- ETAPE 6 : GESTION DU FICHIER ---
            print("[INFO] Waiting for file transfer...")
            existing = set(f.name.lower() for f in DOWNLOADS_DIR.iterdir() if f.is_file()) if DOWNLOADS_DIR.exists() else set()
            i_data = None
            for _ in range(60):
                await asyncio.sleep(1)
                if d_task:
                    t_f = TEMP_DIR / f"gemini_final_{int(time.time())}.png"
                    await d_task.save_as(str(t_f))
                    if t_f.stat().st_size > 15000:
                        erase_gemini_watermark(str(t_f))
                        i_data = t_f.read_bytes(); break
                for f in DOWNLOADS_DIR.iterdir():
                    if f.is_file() and f.name.lower() not in existing:
                        if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp'] and f.stat().st_size > 15000:
                            erase_gemini_watermark(str(f))
                            i_data = f.read_bytes(); break
                if i_data: break

            if i_data:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                fn = f"gemini_{ts}.png"
                b64 = base64.b64encode(i_data).decode("utf-8")
                r = requests.put(f"{GITHUB_API_URL}/{fn}", headers=HEADERS, json={"message": f"Gen {fn}", "content": b64, "branch": GITHUB_BRANCH})
                if r.status_code in (200, 201): print(f"[RESULT] {RAW_BASE_URL}/{fn}")
                else: print(f"[ERROR] GitHub failed ({r.status_code})")
            else:
                print("[ERROR] Image generated but download sync failed.")

    except Exception as e:
        print(f"[ERROR] Fatal Exception: {e}")
    finally:
        print("\n[INFO] SCRIPT FINISHED. BROWSER REMAINS OPEN.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        Path(PROMPT_FILE).write_text(sys.argv[1], encoding="utf-8")
    asyncio.run(main())
