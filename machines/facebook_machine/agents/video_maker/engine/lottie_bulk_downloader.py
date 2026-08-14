# lottie_bulk_downloader.py
# Télécharge ~120 animations Lottie depuis 2 sources confirmées sans Cloudflare :
#   1. useAnimations GitHub (56 icônes, 100% fiable)
#   2. LottieFiles CDN (hashes validés, avec Referer)
#
# Usage :
#   python cinema/lottie_bulk_downloader.py
#   python cinema/lottie_bulk_downloader.py --force   (re-télécharge tout)
#   python cinema/lottie_bulk_downloader.py --dry-run (test sans écriture)

import json
import time
import argparse
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
BULK_DIR  = Path(__file__).parent.parent / "assets" / "lottie" / "bulk"
LOCAL_MAP = Path(__file__).parent.parent / "assets" / "lottie" / "local_map.json"
DELAY     = 0.3
TIMEOUT   = 12

REFERER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0",
    "Referer":    "https://lottiefiles.com/",
    "Origin":     "https://lottiefiles.com",
    "Accept":     "application/json, */*",
}

GITHUB_HEADERS = {"User-Agent": "Mozilla/5.0"}

# ---------------------------------------------------------------------------
# SOURCE 1 : useAnimations GitHub (56 icônes confirmées)
# format : https://raw.githubusercontent.com/useAnimations/react-useanimations/master/src/lib/{name}/{name}.json
# ---------------------------------------------------------------------------
USE_ANIMATIONS_ICONS = [
    "activity", "alertCircle", "alertTriangle", "archive", "arrowDown", "arrowUp",
    "bookmark", "calendar", "checkBox", "checkmark", "download", "edit", "error",
    "explore", "facebook", "folder", "github", "heart", "help", "home", "infinity",
    "info", "instagram", "linkedin", "loading", "loading2", "loading3", "lock",
    "mail", "menu", "menu2", "menu3", "menu4", "microphone", "notification",
    "notification2", "playPause", "plusToX", "radioButton", "scrollDown", "searchToX",
    "settings", "settings2", "share", "star", "thumbUp", "toggle", "trash", "trash2",
    "twitter", "video", "visibility", "volume", "youtube", "zoomIn", "zoomOut",
]

UA_BASE = (
    "https://raw.githubusercontent.com/useAnimations/react-useanimations"
    "/master/src/lib/{name}/{name}.json"
)

# ---------------------------------------------------------------------------
# SOURCE 2 : LottieFiles CDN (hashes validés avec Referer)
# ---------------------------------------------------------------------------
CDN_BASE = "https://assets1.lottiefiles.com/packages/{hash}.json"

# Hashes originaux (lottie_library.py)
CDN_ORIGINAL = [
    "lf20_jbrw3hcz", "lf20_obhph3sh", "lf20_rovf9gzu", "lf20_puciaact",
    "lf20_touohxv0", "lf20_fcfjwiyb", "lf20_xyadoh9h", "lf20_syqnfe7c",
    "lf20_xlmz9xwm", "lf20_qp1q7mct", "lf20_DMgKk1",  "lf20_pqnfmone",
    "lf20_atqzipf0", "lf20_06a6pf9i", "lf20_qm8eqzse", "lf20_jcikwtux",
    "lf20_sbts4qng", "lf20_t9gkkhz4", "lf20_V9t630",  "lf20_ikga4ytd",
]

# Nouveaux hashes (extraits de repos LottieFiles officiels, 40/41 validés)
CDN_NEW = [
    "lf20_2m1smtya", "lf20_4fET62",   "lf20_7ex5ufle", "lf20_7zara4iv",
    "lf20_8sn2ymow", "lf20_9WL4VQ",   "lf20_9ZfVw0",   "lf20_FISfBK",
    "lf20_ISbOsd",   "lf20_QpeChC",   "lf20_RItkEz",   "lf20_UJNc2t",
    "lf20_bshezgfo", "lf20_dmd1gncl", "lf20_fj8rlma5", "lf20_fwgp2r4s",
    "lf20_gb5bmwlm", "lf20_gr2cHM",   "lf20_i9mxcD",   "lf20_ioxyd2gs",
    "lf20_jicJD5",   "lf20_lmceydcv", "lf20_lxd6qbf3", "lf20_mjuuisyd",
    "lf20_mrg9xhbm", "lf20_nc99k6bp", "lf20_opn6z1qt", "lf20_pKiaUR",
    "lf20_prxhhnpq", "lf20_qj6ywemr", "lf20_sefbiwsx", "lf20_tn8qikk9",
    "lf20_tnt528ff", "lf20_tzjfwgud", "lf20_u4j3xm6r", "lf20_v4yd7sef",
    "lf20_vowsuuvc", "lf20_zPo7NV",   "lf20_zwath9pn", "lf20_zyquagfl",
]

ALL_CDN_HASHES = list(dict.fromkeys(CDN_ORIGINAL + CDN_NEW))  # dédupliqué

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _is_valid_lottie(data) -> bool:
    return (
        isinstance(data, dict)
        and "v" in data
        and "layers" in data
        and isinstance(data.get("layers"), list)
        and len(data["layers"]) > 0
    )


def _load_local_map() -> dict:
    if LOCAL_MAP.exists():
        try:
            return json.loads(LOCAL_MAP.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_local_map(local_map: dict):
    LOCAL_MAP.write_text(
        json.dumps(local_map, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# DOWNLOAD FUNCTIONS
# ---------------------------------------------------------------------------

def download_use_animations(dry_run: bool, force: bool) -> tuple[int, int]:
    """Télécharge les 56 icônes useAnimations. Retourne (ok, fail)."""
    print(f"\n[SOURCE 1] useAnimations GitHub — {len(USE_ANIMATIONS_ICONS)} icônes")
    print("-" * 60)

    ok = fail = 0
    for name in USE_ANIMATIONS_ICONS:
        out_path = BULK_DIR / f"ua_{name}.json"
        if out_path.exists() and not force:
            ok += 1
            print(f"  SKIP {name}")
            continue

        url = UA_BASE.format(name=name)
        try:
            time.sleep(DELAY)
            r = requests.get(url, headers=GITHUB_HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                if _is_valid_lottie(data):
                    if not dry_run:
                        out_path.write_text(
                            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8"
                        )
                    size = len(r.content) // 1024
                    print(f"  OK  {name:<20} {size}KB")
                    ok += 1
                else:
                    print(f"  INVALID {name}")
                    fail += 1
            else:
                print(f"  FAIL {name} ({r.status_code})")
                fail += 1
        except Exception as e:
            print(f"  ERR  {name}: {e}")
            fail += 1

    print(f"  --> {ok} OK / {fail} FAIL")
    return ok, fail


def download_cdn_hashes(dry_run: bool, force: bool) -> tuple[int, int]:
    """Télécharge les hashes LottieFiles CDN. Retourne (ok, fail)."""
    print(f"\n[SOURCE 2] LottieFiles CDN — {len(ALL_CDN_HASHES)} hashes")
    print("-" * 60)

    ok = fail = 0
    for h in ALL_CDN_HASHES:
        out_path = BULK_DIR / f"cdn_{h}.json"
        if out_path.exists() and not force:
            ok += 1
            print(f"  SKIP {h}")
            continue

        # Essai sur assets1, puis assets2, assets3
        downloaded = False
        for cdn_num in (1, 2, 3, 4, 9):
            url = f"https://assets{cdn_num}.lottiefiles.com/packages/{h}.json"
            try:
                time.sleep(DELAY)
                r = requests.get(url, headers=REFERER_HEADERS, timeout=TIMEOUT)
                if r.status_code == 200:
                    data = r.json()
                    if _is_valid_lottie(data):
                        if not dry_run:
                            out_path.write_text(
                                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                                encoding="utf-8"
                            )
                        size = len(r.content) // 1024
                        print(f"  OK  {h:<20} {size}KB  (assets{cdn_num})")
                        ok += 1
                        downloaded = True
                        break
            except Exception:
                pass

        if not downloaded:
            print(f"  FAIL {h}")
            fail += 1

    print(f"  --> {ok} OK / {fail} FAIL")
    return ok, fail


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def bulk_download(dry_run: bool = False, force: bool = False):
    BULK_DIR.mkdir(parents=True, exist_ok=True)
    local_map = _load_local_map()

    total_sources = len(USE_ANIMATIONS_ICONS) + len(ALL_CDN_HASHES)

    print(f"\n{'='*60}")
    print(f"  LOTTIE BULK DOWNLOADER")
    print(f"  useAnimations : {len(USE_ANIMATIONS_ICONS)} icônes")
    print(f"  LottieFiles CDN : {len(ALL_CDN_HASHES)} hashes")
    print(f"  Total visé      : {total_sources} animations")
    print(f"  Mode : {'DRY RUN' if dry_run else 'ÉCRITURE'}")
    print(f"{'='*60}")

    ok1, fail1 = download_use_animations(dry_run, force)
    ok2, fail2 = download_cdn_hashes(dry_run, force)

    total_ok = ok1 + ok2
    total_fail = fail1 + fail2
    total_files = len(list(BULK_DIR.glob("*.json")))

    # Ajouter les nouveaux fichiers dans local_map sous des clés génériques
    if not dry_run:
        # useAnimations → clé "ua_<name>"
        for name in USE_ANIMATIONS_ICONS:
            p = BULK_DIR / f"ua_{name}.json"
            if p.exists():
                local_map[f"ua_{name}"] = str(p.resolve())
        # CDN → clé "cdn_<hash>"
        for h in ALL_CDN_HASHES:
            p = BULK_DIR / f"cdn_{h}.json"
            if p.exists():
                local_map[f"cdn_{h}"] = str(p.resolve())
        _save_local_map(local_map)

    print(f"\n{'='*60}")
    print(f"  RAPPORT FINAL")
    print(f"  OK     : {total_ok}")
    print(f"  FAIL   : {total_fail}")
    print(f"  Total fichiers bulk/ : {total_files}")
    print(f"  local_map.json mis à jour")
    print(f"{'='*60}\n")

    return total_ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force",   action="store_true")
    args = parser.parse_args()
    bulk_download(dry_run=args.dry_run, force=args.force)
