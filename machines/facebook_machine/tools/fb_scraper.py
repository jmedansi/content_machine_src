# fb_scraper.py — Scrape les posts publics des pages Facebook cibles
# Usage : python tools/fb_scraper.py
# Prerequis : etre connecte a Facebook dans le Chrome du generateur d'images
# Resultat : tools/scraped/<slug>.json

import json
import os
import re
import shutil
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Dossier source = profil Chrome du generateur d'images (Default)
CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", "")
# Copie temporaire du profil pour eviter le blocage CDP
PROFILE_COPY_DIR = Path(__file__).parent / "_chrome_profile_tmp"

OUT_DIR = Path(__file__).parent / "scraped"
OUT_DIR.mkdir(exist_ok=True)

PAGES = [
    {"slug": "kebane",    "url": "https://www.facebook.com/kebaneloemba"},
    {"slug": "niche_ia1", "url": "https://www.facebook.com/profile.php?id=61562708253269"},
    {"slug": "owwstin",   "url": "https://www.facebook.com/Owwstin"},
    {"slug": "yikchan",   "url": "https://www.facebook.com/yikchanltd"},
]

MAX_POSTS   = 35
MAX_SCROLLS = 30

UI_NOISE = [
    "Voir plus", "See more", "J'aime", "Like", "Commenter", "Comment",
    "Partager", "Share", "Reagir", "React", "Reponses", "Replies",
    "Vue d'ensemble", "A propos", "Videos", "Photos", "Publications",
    "Suivre", "Follow", "Message", "Plus", "More", "Tout afficher",
    "Fil d'actualite", "Groupes", "Marketplace", "Watch", "Events",
    "Publicites", "Jeux", "Connexion", "S'inscrire",
]


def _clean(text: str) -> str:
    for n in UI_NOISE:
        text = text.replace(n, " ")
    return re.sub(r'\s+', ' ', text).strip()


def _copy_profile():
    """Copie uniquement les fichiers necessaires du profil Default."""
    src = Path(CHROME_USER_DATA_DIR) / "Profile 10"
    dst = PROFILE_COPY_DIR / "Default"

    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)

    # Copier seulement les fichiers essentiels pour les cookies/session
    files_to_copy = ["Cookies", "Local Storage", "Session Storage",
                     "Network", "Preferences", "Secure Preferences"]
    for name in files_to_copy:
        s = src / name
        d = dst / name
        if s.is_file():
            shutil.copy2(s, d)
        elif s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True)

    # Copier Local State (cle AES) au niveau User Data
    ls_src = Path(CHROME_USER_DATA_DIR) / "Local State"
    ls_dst = PROFILE_COPY_DIR / "Local State"
    if ls_src.exists():
        shutil.copy2(ls_src, ls_dst)

    print(f"Profil copie dans : {PROFILE_COPY_DIR}")


def scrape_page(ctx, slug: str, url: str) -> list[dict]:
    posts = []
    print(f"\n[{slug}] Scraping {url}")

    page = ctx.new_page()
    page.route("**/*.{png,jpg,jpeg,gif,webp,mp4,mp3,woff,woff2}", lambda r: r.abort())

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
    except Exception as e:
        print(f"  [!] Timeout : {e}")

    page.wait_for_timeout(3000)

    for selector in ['div[role="dialog"] button', '[aria-label="Fermer"]']:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1000):
                btn.click()
                page.wait_for_timeout(500)
        except Exception:
            pass

    seen_texts = set()
    scrolls = 0
    stale = 0

    while len(posts) < MAX_POSTS and scrolls < MAX_SCROLLS:
        articles = page.locator('[role="article"]').all()
        prev = len(posts)

        for art in articles:
            try:
                raw = art.inner_text(timeout=800)
                if not raw or len(raw) < 40:
                    continue
                text = _clean(raw)
                key = text[:100]
                if key in seen_texts or len(text) < 40:
                    continue
                if any(kw in text[:150] for kw in ["Fil d", "Groupes", "Marketplace", "Connexion"]):
                    continue
                seen_texts.add(key)
                posts.append({"text": text, "source": slug})
            except Exception:
                pass

        if len(posts) == prev:
            stale += 1
            if stale >= 5:
                print(f"  Plus de nouveaux posts, arret.")
                break
        else:
            stale = 0

        page.evaluate("window.scrollBy(0, 1400)")
        time.sleep(1.5)
        scrolls += 1

        if scrolls % 5 == 0:
            print(f"  scroll {scrolls}/{MAX_SCROLLS} -- {len(posts)} posts...")

    page.close()
    print(f"  -> {len(posts)} posts extraits pour '{slug}'")
    return posts


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        print("Connexion au Chrome actif sur port 9222...")
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.contexts[0]

        all_results = {}
        for cfg in PAGES:
            posts = scrape_page(ctx, cfg["slug"], cfg["url"])
            all_results[cfg["slug"]] = posts
            out_file = OUT_DIR / f"{cfg['slug']}.json"
            out_file.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  Sauvegarde : {out_file}")

        browser.close()

    consolidated = OUT_DIR / "_all.json"
    consolidated.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v) for v in all_results.values())
    print(f"\nTermine. {total} posts collectes sur {len(PAGES)} pages.")
    print("Prochaine etape : python tools/fb_analyzer.py")


if __name__ == "__main__":
    main()
