import asyncio
import os
import time
import base64
import subprocess
import socket
import sys
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import requests

try:
    from watermark_tool import erase_gemini_watermark
except ImportError:
    def erase_gemini_watermark(p, output_path=None): pass

# Fix encoding
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# Config
GEMINI_URL = "https://gemini.google.com/app"
UPLOADS_DIR = Path("uploads")
DOWNLOADS_DIR = Path("C:/Users/jmeda/Downloads")
GITHUB_REPO = "jmedansi/temp"
GITHUB_BRANCH = "main"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents"
RAW_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
CHROME_DEBUG_PORT = 9222

# Délai max d'attente de la génération Gemini (secondes)
GEMINI_MAX_WAIT = 300  # 5 min
# Nombre de tentatives automatiques en cas d'échec
MAX_RETRIES = 3

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"} if GITHUB_TOKEN else {}

class GeminiEngine:
    def __init__(self):
        UPLOADS_DIR.mkdir(exist_ok=True)

    def is_port_open(self, port=CHROME_DEBUG_PORT):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    def launch_chrome(self):
        if self.is_port_open(): return True
        print("[INFO] Lancement Chrome...")
        chrome_path = "C:/Program Files/Google/Chrome/Application/chrome.exe"
        data_dir = os.path.expandvars("%LOCALAPPDATA%/Google/Chrome/User Data")
        profile = os.path.join(data_dir, "Profile 1")
        
        subprocess.Popen([
            chrome_path, f"--remote-debugging-port={CHROME_DEBUG_PORT}",
            f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
            "--disable-session-crashed-bubble", "--disable-infobars"
        ])
        for _ in range(15):
            time.sleep(1)
            if self.is_port_open(): return True
        return False

    async def _detect_blocking_page(self, page):
        """
        Détecte si Gemini affiche une page bloquante (anti-robot, erreur, quota).
        Utilise des sélecteurs DOM précis pour éviter les faux positifs.
        """
        try:
            # Captcha Google / reCAPTCHA (iframe spécifique)
            captcha = await page.query_selector('iframe[src*="recaptcha"], iframe[src*="captcha"]')
            if captcha:
                return "anti-robot"

            # Page "unusual traffic" Google (URL spécifique)
            if "sorry.google.com" in page.url or "accounts.google.com/v3/signin" in page.url:
                return "anti-robot-redirect"

            # Erreur Gemini visible dans l'UI (composant d'erreur natif)
            error_el = await page.query_selector(
                '[data-test-id="error-message"], '
                '.error-container, '
                'snack-bar-container.mat-snack-bar-container'
            )
            if error_el and await error_el.is_visible():
                error_text = (await error_el.text_content() or "").strip()
                if any(kw in error_text.lower() for kw in ["quota", "limit", "rate", "too many", "trop de"]):
                    return "quota-exceeded"
                if error_text:
                    return f"gemini-error: {error_text[:100]}"

            return None
        except:
            return None

    async def _run_once(self, prompt, local_image=None, mode="generate"):
        """
        Exécute une tentative unique. Retourne un dict {url} ou lève une exception.
        """
        async with async_playwright() as p:
            if not self.launch_chrome():
                raise RuntimeError("Chrome failed to start")
            
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0]

            # Réutiliser un onglet déjà ouvert sur Gemini pour paraître moins suspect
            page = None
            for existing_page in context.pages:
                if "gemini.google.com" in existing_page.url:
                    page = existing_page
                    print("[INFO] Réutilisation de l'onglet Gemini existant.")
                    break
            if page is None:
                page = await context.new_page()

            d_task = None
            def on_d(d): nonlocal d_task; d_task = d
            page.on("download", on_d)

            print(f"[INFO] Mode {mode.upper()} : Navigation Gemini...")
            try:
                await page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
            except PlaywrightTimeout:
                raise RuntimeError("Timeout lors du chargement de Gemini (réseau ?)")
            
            await page.wait_for_timeout(3000)

            # Vérification anti-robot / page bloquante AVANT toute action
            block = await self._detect_blocking_page(page)
            if block:
                await page.close()
                raise RuntimeError(f"Page bloquante détectée : {block}")

            # Sélection du textbox
            try:
                chat_input = await page.wait_for_selector('div[role="textbox"]', timeout=10000)
            except PlaywrightTimeout:
                await page.close()
                raise RuntimeError("Textbox Gemini introuvable — interface non chargée ?")

            await chat_input.click()
            await chat_input.fill("")

            if mode == "generate":
                # Mode Image : cliquer sur la card "Generate image"
                cards = await page.query_selector_all('button.card-zero-state')
                for card in cards:
                    if "image" in (await card.text_content()).lower():
                        await card.click(); break
            else:
                # Mode Modification : injection par copier-coller virtuel
                print(f"[INFO] Mode Modification : Injection par clipboard de {local_image}...")
                try:
                    with open(local_image, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode("utf-8")
                    
                    js_paste = """(b64Data) => {
                        const b64toBlob = (b64Data, contentType='', sliceSize=512) => {
                            const byteCharacters = atob(b64Data);
                            const byteArrays = [];
                            for (let offset = 0; offset < byteCharacters.length; offset += sliceSize) {
                                const slice = byteCharacters.slice(offset, offset + sliceSize);
                                const byteNumbers = new Array(slice.length);
                                for (let i = 0; i < slice.length; i++) {
                                    byteNumbers[i] = slice.charCodeAt(i);
                                }
                                byteArrays.push(new Uint8Array(byteNumbers));
                            }
                            return new Blob(byteArrays, {type: contentType});
                        };
                        const blob = b64toBlob(b64Data, 'image/png');
                        const file = new File([blob], 'image.png', { type: 'image/png' });
                        const dt = new DataTransfer();
                        dt.items.add(file);
                        const target = document.querySelector('div[role="textbox"]');
                        target.focus();
                        const pasteEvent = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
                        target.dispatchEvent(pasteEvent);
                    }"""
                    await page.evaluate(js_paste, b64_data)
                    print("[INFO] Image collée. Attente de la miniature...")
                    await page.wait_for_timeout(6000)
                except Exception as e:
                    await page.close()
                    raise RuntimeError(f"Échec de l'injection clipboard : {e}")

            # Envoi du prompt
            print(f"[INFO] Saisie du prompt...")
            await chat_input.click()
            await page.keyboard.insert_text(prompt)
            
            # Soumission avec retry + fallback JS
            submitted = False
            
            # Méthode 1: Cliquer sur le bouton Send (si présent)
            s_btn = await page.query_selector('button[aria-label*="Send"], button[aria-label*="Envoyer"]')
            if s_btn:
                await s_btn.click()
                submitted = True
                print("[INFO] Soumis via bouton Send")
            
            # Méthode 2: Si pas de bouton, utiliser Enter avec retry
            if not submitted:
                for attempt in range(3):
                    await chat_input.focus()
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(1500)
                    
                    # Vérifier si la soumission a fonctionné
                    stop_btn = await page.query_selector('button[aria-label*="Stop"], button[aria-label*="Arrêter"]')
                    generating = await page.query_selector('div[aria-label*="Generating"], div[role="progressbar"]')
                    
                    if stop_btn or generating:
                        submitted = True
                        print(f"[INFO] Soumis via Enter (tentative {attempt + 1})")
                        break
                    
                    await page.wait_for_timeout(500)
            
            # Méthode 3: Fallback JavaScript si les deux méthodes ont échoué
            if not submitted:
                print("[INFO] Retry via JavaScript...")
                submit_js = """
                () => {
                    const input = document.querySelector('div[role="textbox"]');
                    if (input) {
                        input.focus();
                        const event = new KeyboardEvent('keydown', {
                            key: 'Enter',
                            code: 'Enter',
                            keyCode: 13,
                            which: 13,
                            bubbles: true
                        });
                        input.dispatchEvent(event);
                    }
                }
                """
                await page.evaluate(submit_js)
                await page.wait_for_timeout(2000)
                print("[INFO] Soumis via JavaScript")
            
            # Vérification que la génération a commencé
            await page.wait_for_timeout(3000)
            stop_btn = await page.query_selector('button[aria-label*="Stop"], button[aria-label*="Arrêter"]')
            generating = await page.query_selector('div[role="progressbar"]')
            if not stop_btn and not generating:
                raise RuntimeError("Échec de la soumission du prompt")

            # Monitoring — attente de la fin de génération
            print(f"[INFO] Attente de la génération (max {GEMINI_MAX_WAIT}s)...")
            found_done = False
            for tick in range(GEMINI_MAX_WAIT):
                # Vérification anti-bloc toutes les 30 secondes
                if tick > 0 and tick % 30 == 0:
                    block = await self._detect_blocking_page(page)
                    if block:
                        await page.close()
                        raise RuntimeError(f"Interruption détectée après {tick}s : {block}")

                stop_btn = await page.query_selector('button[aria-label*="Stop"], button[aria-label*="Arrêter"]')
                signals = await page.query_selector_all('button[aria-label*="response"], button[aria-label*="réponse"]')
                
                if (not stop_btn or not await stop_btn.is_visible()) and len(signals) > 0:
                    found_done = True
                    break
                
                await asyncio.sleep(1)

            if not found_done:
                await page.close()
                raise RuntimeError(f"Timeout : Gemini n'a pas terminé en {GEMINI_MAX_WAIT}s")

            # Téléchargement de l'image générée
            print("[INFO] Téléchargement de l'image (15 essais)...")
            await asyncio.sleep(5)
            img_data = None

            for retry in range(15):
                try:
                    img_btn = await page.wait_for_selector('button.image-button', state="attached", timeout=5000)
                    if img_btn:
                        await img_btn.hover(force=True)
                        await page.wait_for_timeout(3000)
                        d_btn = await page.query_selector('button[aria-label*="Download"], button[aria-label*="Télécharger"]')
                        if d_btn:
                            await d_btn.click()
                            print("[INFO] Download déclenché.")
                            existing = set(f.name.lower() for f in DOWNLOADS_DIR.iterdir() if f.is_file())
                            for _ in range(40):
                                await asyncio.sleep(1)
                                if d_task:
                                    t_f = UPLOADS_DIR / f"result_{int(time.time())}.png"
                                    await d_task.save_as(str(t_f))
                                    erase_gemini_watermark(str(t_f))
                                    img_data = t_f.read_bytes()
                                    break
                                # Fallback : scan du dossier de téléchargements
                                for f in DOWNLOADS_DIR.iterdir():
                                    if f.name.lower() not in existing and f.stat().st_size > 15000:
                                        erase_gemini_watermark(str(f))
                                        img_data = f.read_bytes()
                                        break
                    if img_data:
                        break
                except Exception:
                    pass
                await asyncio.sleep(2)

            await page.close()

            if not img_data:
                raise RuntimeError("Impossible de télécharger l'image générée")

            # Upload GitHub
            fn = f"gemini_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            b64 = base64.b64encode(img_data).decode("utf-8")
            r = requests.put(
                f"{GITHUB_API_URL}/{fn}",
                headers=HEADERS,
                json={"message": f"Gen {fn}", "content": b64, "branch": GITHUB_BRANCH},
                timeout=30
            )
            
            if r.status_code in (200, 201):
                return {"url": f"{RAW_BASE_URL}/{fn}"}
            else:
                raise RuntimeError(f"GITHUB_ERROR: {r.status_code}")

    async def run(self, prompt, local_image=None, mode="generate"):
        """
        Point d'entrée principal avec système de retry automatique.
        En cas d'erreur (anti-robot, timeout, réseau), ferme la page et réessaie.
        """
        last_error = "UNKNOWN_ERROR"

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"[INFO] Tentative {attempt}/{MAX_RETRIES}...")
                result = await self._run_once(prompt, local_image=local_image, mode=mode)
                print(f"[SUCCESS] Résultat obtenu à la tentative {attempt}.")
                return result
            except RuntimeError as e:
                last_error = str(e)
                print(f"[WARN] Tentative {attempt} échouée : {last_error}")
                
                # S'arrêter immédiatement si c'est un anti-robot ou quota pour ne pas aggraver le cas
                if any(kw in last_error for kw in ["anti-robot", "quota", "captcha"]):
                    print(f"[CRITICAL] Blocage de sécurité détecté : {last_error}")
                    return {"error": last_error}

                # Pause progressive standard (2s, 5s, 10s)
                wait = [0, 2, 5, 10][attempt]
                
                if attempt < MAX_RETRIES:
                    print(f"[INFO] Reprise dans {wait}s...")
                    await asyncio.sleep(wait)

        print(f"[ERROR] Toutes les tentatives ont échoué. Dernière erreur : {last_error}")
        return {"error": last_error}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", "-i", default=None, help="Path to local image to modify")
    parser.add_argument("--mode", "-m", default="generate", choices=["generate", "modify"], help="Generation mode")
    parser.add_argument("prompt", nargs="?", default="")
    args = parser.parse_args()
    
    engine = GeminiEngine()
    if args.image:
        mode = "modify"
        local_image = args.image
    else:
        mode = "generate"
        local_image = None
    
    result = asyncio.run(engine.run(args.prompt, local_image=local_image, mode=mode))
    if result.get("url"):
        print(f"[RESULT] {result['url']}")
    else:
        print(f"[ERROR] {result.get('error', 'Unknown error')}")
