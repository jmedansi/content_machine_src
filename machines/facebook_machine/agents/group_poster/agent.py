# agent.py — Partage automatique des posts de la Page dans des groupes Facebook
# Stratégie : un profil tiers (Chrome séparé) partage le dernier post de la Page
# dans les groupes configurés via Playwright.
import sys
import json
import random
import time
from pathlib import Path
from datetime import datetime, date

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from core.models import AgentResult
from core.config import Config
from core.logger import get_node_logger

logger = get_node_logger("group_poster")

GROUPS_FILE  = Config.DATA_DIR / "facebook_groups.json"
SHARE_LOG    = Config.DATA_DIR / "group_share_log.json"

# ── Sélecteurs Playwright ──────────────────────────────────────────────────────

# Bouton "Partager" sous un post
SELECTORS_SHARE_BTN = [
    '[aria-label="Envoyer ce post à des amis ou le publier sur un profil."]',
    '[aria-label*="Partager"]',
    'div[role="button"]:has-text("Partager")',
    'span:has-text("Partager")',
]

# Option "Partager dans un groupe" dans le menu déroulant
SELECTORS_SHARE_IN_GROUP = [
    'span:has-text("Partager dans un groupe")',
    'div[role="menuitem"]:has-text("groupe")',
    'a:has-text("Partager dans un groupe")',
]

# Champ de recherche du groupe dans la modal de partage
SELECTORS_GROUP_SEARCH = [
    'input[placeholder*="Chercher"]',
    'input[placeholder*="groupe"]',
    'input[type="text"]',
]

# Textarea du commentaire optionnel dans la modal
SELECTORS_COMMENT_BOX = [
    'div[contenteditable="true"][role="textbox"]',
    'div[aria-label*="publication"][contenteditable]',
    'div[aria-label*="Dites"][contenteditable]',
]

# Bouton "Publier" / "Partager maintenant" dans la modal
SELECTORS_PUBLISH = [
    'div[aria-label="Publier"]',
    'div[aria-label="Partager maintenant"]',
    'button:has-text("Partager maintenant")',
    'button:has-text("Publier")',
    'div[role="button"]:has-text("Partager maintenant")',
    'div[role="button"]:has-text("Publier")',
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_groups() -> list:
    if GROUPS_FILE.exists():
        return json.loads(GROUPS_FILE.read_text(encoding="utf-8"))
    return []


def load_share_log() -> dict:
    if SHARE_LOG.exists():
        try:
            return json.loads(SHARE_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_share_log(data: dict):
    SHARE_LOG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_latest_published_post_url() -> str | None:
    """Récupère l'URL du dernier post publié depuis les dossiers content/."""
    content_dir = Config.CONTENT_DIR
    if not content_dir.exists():
        return None

    folders = sorted(
        [d for d in content_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True
    )

    for folder in folders:
        meta_file = folder / "meta.json"
        if not meta_file.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if not meta.get("published", False):
                continue
            post_id = meta.get("facebook_post_id", "")
            if not post_id or post_id.startswith("make_") or post_id.startswith("reel_"):
                continue
            # post_id format: "PAGE_ID_POST_ID" → extraire la partie après le _
            page_id = Config.FB_PAGE_ID
            # Construire l'URL publique du post
            short_id = post_id.split("_")[-1] if "_" in post_id else post_id
            url = f"https://www.facebook.com/{page_id}/posts/{short_id}"
            logger.info(f"Dernier post publié trouvé : {url} (dossier: {folder.name})")
            return url
        except Exception:
            continue

    return None


def already_shared_today(group_name: str) -> bool:
    """Vérifie si ce groupe a déjà reçu un partage aujourd'hui."""
    log = load_share_log()
    today = date.today().isoformat()
    shared_today = log.get(today, [])
    return group_name in shared_today


def mark_shared(group_name: str):
    """Marque le groupe comme partagé aujourd'hui."""
    log = load_share_log()
    today = date.today().isoformat()
    if today not in log:
        log[today] = []
    if group_name not in log[today]:
        log[today].append(group_name)
    # Purge les entrées de plus de 7 jours
    cutoff = sorted(log.keys())
    if len(cutoff) > 7:
        for old_key in cutoff[:-7]:
            del log[old_key]
    save_share_log(log)


def find_element(page, selectors: list, timeout: int = 5000):
    for selector in selectors:
        try:
            el = page.locator(selector).first
            if el.count() > 0:
                el.wait_for(timeout=timeout)
                return el
        except Exception:
            continue
    return None


def type_human(page, text: str):
    """Tape le texte comme un humain avec des délais variables."""
    page.keyboard.type(text, delay=random.randint(40, 90))
    page.wait_for_timeout(random.randint(600, 1500))


# ── Logique de partage ────────────────────────────────────────────────────────

def share_post_to_group(page, post_url: str, group_name: str, comment: str = "") -> bool:
    """
    Navigue sur le post de la Page et le partage dans le groupe spécifié.
    Retourne True si le partage a réussi.
    """
    try:
        logger.info(f"Navigation vers le post : {post_url}")
        page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(random.randint(2000, 4000))

        # ── Cliquer sur "Partager" ────────────────────────────────────────────
        share_btn = find_element(page, SELECTORS_SHARE_BTN, timeout=8000)
        if not share_btn:
            logger.error("Bouton Partager introuvable")
            return False

        share_btn.click()
        page.wait_for_timeout(random.randint(1000, 2000))

        # ── Sélectionner "Partager dans un groupe" ───────────────────────────
        group_option = find_element(page, SELECTORS_SHARE_IN_GROUP, timeout=5000)
        if not group_option:
            logger.error("Option 'Partager dans un groupe' introuvable")
            # Fermer le menu si ouvert
            page.keyboard.press("Escape")
            return False

        group_option.click()
        page.wait_for_timeout(random.randint(1500, 2500))

        # ── Chercher le groupe par nom ────────────────────────────────────────
        search_box = find_element(page, SELECTORS_GROUP_SEARCH, timeout=6000)
        if not search_box:
            logger.error("Champ de recherche de groupe introuvable")
            page.keyboard.press("Escape")
            return False

        search_box.click()
        page.wait_for_timeout(500)
        type_human(page, group_name[:30])  # Facebook tronque la recherche de toute façon
        page.wait_for_timeout(random.randint(1500, 2500))

        # Sélectionner le premier résultat correspondant
        group_result = page.locator(f'span:has-text("{group_name[:20]}")').first
        if group_result.count() == 0:
            # Fallback : premier résultat dans la liste
            group_result = page.locator('li[role="option"]').first
        if group_result.count() > 0:
            group_result.click()
            page.wait_for_timeout(random.randint(800, 1500))
        else:
            logger.error(f"Groupe '{group_name}' non trouvé dans les résultats")
            page.keyboard.press("Escape")
            return False

        # ── Ajouter un commentaire optionnel ─────────────────────────────────
        if comment:
            comment_box = find_element(page, SELECTORS_COMMENT_BOX, timeout=4000)
            if comment_box:
                comment_box.click()
                page.wait_for_timeout(500)
                type_human(page, comment)

        # ── Publier / Partager maintenant ─────────────────────────────────────
        publish_btn = find_element(page, SELECTORS_PUBLISH, timeout=6000)
        if not publish_btn:
            logger.error("Bouton Publier/Partager introuvable")
            page.keyboard.press("Escape")
            return False

        publish_btn.click()
        page.wait_for_timeout(random.randint(3000, 5000))

        logger.info(f"✅ Post partagé dans '{group_name}'")
        return True

    except Exception as e:
        logger.error(f"Erreur share_post_to_group ({group_name}): {e}")
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False


# ── Point d'entrée ─────────────────────────────────────────────────────────────

def run_group_poster(post_url: str = "", comment: str = "") -> AgentResult:
    """
    Partage le dernier post publié de la Page dans les groupes configurés.

    Args:
        post_url : URL du post à partager (optionnel, auto-détecté si vide)
        comment  : Commentaire à ajouter au partage (optionnel)
    """
    # ── Profil Chrome du compte tiers ─────────────────────────────────────────
    chrome_profile = os.getenv("GROUP_POSTER_CHROME_PROFILE", Config.CHROME_USER_DATA_DIR)
    if not chrome_profile:
        return AgentResult.fail("GROUP_POSTER_CHROME_PROFILE ou CHROME_USER_DATA_DIR non configuré")

    # ── Groupes cibles ────────────────────────────────────────────────────────
    groups = load_groups()
    if not groups:
        return AgentResult.fail("Aucun groupe dans data/facebook_groups.json")

    # Filtrer ceux déjà partagés aujourd'hui
    groups_pending = [g for g in groups if not already_shared_today(g.get("name", ""))]
    if not groups_pending:
        return AgentResult.ok({"message": "Tous les groupes ont déjà reçu un partage aujourd'hui", "shared": 0})

    # Limiter au quota journalier
    groups_to_share = random.sample(groups_pending, min(Config.GROUPS_PER_DAY, len(groups_pending)))

    # ── URL du post ───────────────────────────────────────────────────────────
    if not post_url:
        post_url = get_latest_published_post_url()
    if not post_url:
        return AgentResult.fail("Aucun post publié trouvé à partager")

    logger.info(f"Partage de {post_url} dans {len(groups_to_share)} groupes")

    # ── Lancer Playwright ─────────────────────────────────────────────────────
    import os
    from playwright.sync_api import sync_playwright

    shared_count = 0
    consecutive_failures = 0

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=chrome_profile,
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.set_extra_http_headers({"Accept-Language": "fr-FR,fr;q=0.9"})

            for i, group in enumerate(groups_to_share):
                group_name = group.get("name", "")
                group_comment = group.get("default_comment", comment)

                logger.info(f"[{i+1}/{len(groups_to_share)}] Partage dans '{group_name}'")

                success = share_post_to_group(page, post_url, group_name, group_comment)

                if success:
                    mark_shared(group_name)
                    shared_count += 1
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        logger.error("2 échecs consécutifs → arrêt par sécurité anti-spam")
                        break

                # Délai humain entre chaque groupe
                if i < len(groups_to_share) - 1:
                    delay = Config.GROUPS_MIN_DELAY_SECONDS + random.randint(0, 600)
                    logger.info(f"Pause {delay}s avant le prochain groupe...")
                    time.sleep(delay)

            context.close()

        except Exception as e:
            logger.exception("Erreur fatale Playwright")
            return AgentResult.fail(str(e))

    return AgentResult.ok({
        "shared": shared_count,
        "targeted": len(groups_to_share),
        "post_url": post_url,
    })
