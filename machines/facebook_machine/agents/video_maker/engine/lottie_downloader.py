# lottie_downloader.py -- Telecharge et stocke les animations Lottie localement
# Usage : python lottie_downloader.py
#
# Strategie :
# 1. Pour chaque keyword, essaie toutes les URLs candidates avec Referer fix
# 2. Valide que le JSON est un vrai fichier Lottie (cles 'v' et 'layers')
# 3. Sauvegarde dans assets/lottie/{keyword}.json
# 4. Ecrit assets/lottie/local_map.json -> keyword: chemin absolu
# 5. Rapport final : OK / FAIL par keyword

import json
import sys
import time
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).parent))
from lottie_library import LOTTIE_CANDIDATES, LOTTIE_LOCAL_DIR

HEADERS_VARIANTS = [
    # Variante 1 : Referer lottiefiles (debloquer les 403)
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Referer":    "https://lottiefiles.com/",
        "Origin":     "https://lottiefiles.com",
        "Accept":     "application/json, */*",
    },
    # Variante 2 : sans Origin
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Referer":    "https://lottiefiles.com/",
        "Accept":     "application/json, */*",
    },
    # Variante 3 : sans headers
    {
        "User-Agent": "Mozilla/5.0",
        "Accept":     "application/json, */*",
    },
]

TIMEOUT = 12  # secondes par requete
DELAY   = 0.3  # pause entre requetes (respect serveur)


def _is_valid_lottie(data: dict) -> bool:
    """Verifie qu'un JSON est un fichier Lottie valide."""
    return (
        isinstance(data, dict)
        and "v" in data
        and "layers" in data
        and isinstance(data["layers"], list)
    )


def _try_download(url: str) -> dict | None:
    """Essaie de telecharger + valider une URL Lottie. Retourne le JSON ou None."""
    for headers in HEADERS_VARIANTS:
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                try:
                    data = r.json()
                    if _is_valid_lottie(data):
                        return data
                except Exception:
                    pass
            elif r.status_code in (403, 404):
                continue  # essayer variante suivante
        except requests.RequestException:
            pass
        time.sleep(0.1)
    return None


def download_all(force: bool = False) -> dict:
    """
    Telecharge toutes les animations de LOTTIE_CANDIDATES.
    force=True : retelecharge meme si deja en local.
    Retourne un dict {keyword: status} avec status 'ok'|'fail'|'skip'.
    """
    LOTTIE_LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    local_map_file = LOTTIE_LOCAL_DIR / "local_map.json"

    # Charger la map locale existante
    local_map = {}
    if local_map_file.exists():
        try:
            local_map = json.loads(local_map_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    results = {}
    total   = len(LOTTIE_CANDIDATES)

    print(f"\n[LOTTIE DL] Debut du telechargement — {total} keywords\n")
    print(f"{'Keyword':<20} {'Status':<8} {'Source'}")
    print("-" * 70)

    for i, (keyword, candidates) in enumerate(LOTTIE_CANDIDATES.items(), 1):
        out_path = LOTTIE_LOCAL_DIR / f"{keyword}.json"

        # Deja en local et pas de force
        if not force and out_path.exists():
            local_map[keyword] = str(out_path.resolve())
            results[keyword] = "skip"
            print(f"[{i:>3}/{total}] {keyword:<20} {'SKIP':<8} (deja en local)")
            continue

        downloaded = False
        for url in candidates:
            time.sleep(DELAY)
            data = _try_download(url)
            if data:
                out_path.write_text(
                    json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8"
                )
                local_map[keyword] = str(out_path.resolve())
                results[keyword] = "ok"
                size_kb = out_path.stat().st_size / 1024
                print(f"[{i:>3}/{total}] {keyword:<20} {'OK':<8} {size_kb:.0f}KB  {url[:55]}")
                downloaded = True
                break

        if not downloaded:
            results[keyword] = "fail"
            print(f"[{i:>3}/{total}] {keyword:<20} {'FAIL':<8} (toutes les URLs ont echoue)")

    # Sauvegarder la map locale
    local_map_file.write_text(
        json.dumps(local_map, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # Rapport final
    ok   = sum(1 for s in results.values() if s == "ok")
    skip = sum(1 for s in results.values() if s == "skip")
    fail = sum(1 for s in results.values() if s == "fail")

    print("\n" + "=" * 70)
    print(f"[LOTTIE DL] RAPPORT FINAL")
    print(f"  Telecharges : {ok}")
    print(f"  Deja en local (skip) : {skip}")
    print(f"  Echecs : {fail}")
    print(f"  TOTAL en stock local : {ok + skip}")
    if fail > 0:
        failed = [k for k, s in results.items() if s == "fail"]
        print(f"  Keywords manquants : {', '.join(failed)}")
    print(f"\n  Fichiers sauvegardes dans : {LOTTIE_LOCAL_DIR}")
    print(f"  Map locale : {LOTTIE_LOCAL_DIR / 'local_map.json'}")
    print("=" * 70)

    return results


def retry_failed(results: dict) -> None:
    """Retente uniquement les keywords en echec."""
    failed = [k for k, s in results.items() if s == "fail"]
    if not failed:
        print("[LOTTIE DL] Aucun echec a retenter.")
        return
    print(f"\n[LOTTIE DL] Nouvelle tentative pour {len(failed)} keywords...")
    for keyword in failed:
        candidates = LOTTIE_CANDIDATES.get(keyword, [])
        out_path = LOTTIE_LOCAL_DIR / f"{keyword}.json"
        for url in candidates:
            time.sleep(DELAY * 2)
            data = _try_download(url)
            if data:
                out_path.write_text(
                    json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8"
                )
                print(f"  {keyword:<20} OK (2e tentative)")
                break
        else:
            print(f"  {keyword:<20} FAIL definitif")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Telecharge les animations Lottie en local")
    parser.add_argument("--force", action="store_true", help="Retelecharger meme si deja en local")
    parser.add_argument("--retry", action="store_true", help="Retenter seulement les echecs")
    args = parser.parse_args()

    if args.retry:
        # Charger les resultats precedents depuis local_map et detecter les manquants
        local_map_file = LOTTIE_LOCAL_DIR / "local_map.json"
        existing = set()
        if local_map_file.exists():
            try:
                existing = set(json.loads(local_map_file.read_text()).keys())
            except Exception:
                pass
        fake_results = {k: ("skip" if k in existing else "fail") for k in LOTTIE_CANDIDATES}
        retry_failed(fake_results)
    else:
        results = download_all(force=args.force)

    # Recharger la map apres telechargement
    try:
        from lottie_library import reload_map
        reload_map()
        print("\n[LOTTIE DL] LOTTIE_MAP rechargee avec les fichiers locaux.")
    except Exception as e:
        print(f"\n[LOTTIE DL] Recharge map: {e}")
