# fb_login.py — Extrait les cookies Facebook depuis Chrome Profile 10
# LANCER dans un terminal (Chrome doit etre ferme) :
#   cd d:\Content_Machine\machines/facebook-machine
#   python tools/fb_login.py

import base64
import ctypes
import ctypes.wintypes
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

SESSION_FILE     = Path(__file__).parent / "fb_session.json"
CHROME_USER_DATA = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
CHROME_PROFILE   = "Profile 10"


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_decrypt(data: bytes) -> bytes:
    buf    = ctypes.create_string_buffer(data, len(data))
    blobin = _BLOB(len(data), buf)
    blobout = _BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blobin), None, None, None, None, 0, ctypes.byref(blobout)
    )
    if not ok:
        raise RuntimeError("DPAPI decrypt failed")
    result = ctypes.string_at(blobout.pbData, blobout.cbData)
    ctypes.windll.kernel32.LocalFree(blobout.pbData)
    return result


def _get_aes_key() -> bytes:
    local_state = CHROME_USER_DATA / "Local State"
    data = json.loads(local_state.read_text(encoding="utf-8"))
    enc_key_b64 = data["os_crypt"]["encrypted_key"]
    enc_key = base64.b64decode(enc_key_b64)[5:]  # strip 5-byte DPAPI prefix
    return _dpapi_decrypt(enc_key)


def _decrypt_value(key: bytes, enc_val: bytes) -> str:
    if not enc_val:
        return ""
    # v10/v11 = AES-256-GCM
    if enc_val[:3] in (b"v10", b"v11"):
        from Crypto.Cipher import AES
        nonce     = enc_val[3:15]
        ciphertext = enc_val[15:-16]
        tag       = enc_val[-16:]
        try:
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8", errors="replace")
        except Exception:
            try:
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                return cipher.decrypt(ciphertext).decode("utf-8", errors="replace")
            except Exception:
                return ""
    # Ancien format : DPAPI direct
    try:
        return _dpapi_decrypt(enc_val).decode("utf-8", errors="replace")
    except Exception:
        return ""


def main():
    print("=" * 60)
    print(f"Extraction cookies Facebook -- {CHROME_PROFILE}")
    print("=" * 60)

    # 1. Cle AES depuis Local State
    try:
        key = _get_aes_key()
        print(f"Cle AES obtenue ({len(key)} bytes)")
    except Exception as e:
        print(f"[!] Impossible de lire la cle AES : {e}")
        return

    # 2. Copier le fichier Cookies (Chrome le verrouille sinon)
    cookies_db = CHROME_USER_DATA / CHROME_PROFILE / "Network" / "Cookies"
    if not cookies_db.exists():
        cookies_db = CHROME_USER_DATA / CHROME_PROFILE / "Cookies"
    if not cookies_db.exists():
        print(f"[!] Fichier Cookies introuvable : {cookies_db}")
        return

    tmp = Path(tempfile.mktemp(suffix=".db"))
    shutil.copy2(cookies_db, tmp)
    print(f"Base copiee : {tmp}")

    # 3. Lire et decrypter les cookies Facebook
    cookies = []
    try:
        conn = sqlite3.connect(str(tmp))
        rows = conn.execute(
            "SELECT host_key, name, encrypted_value, path, is_secure, is_httponly "
            "FROM cookies WHERE host_key LIKE '%facebook.com%'"
        ).fetchall()
        conn.close()

        for host, name, enc_val, path, secure, http_only in rows:
            value = _decrypt_value(key, bytes(enc_val))
            if not value:
                continue
            domain = host if host.startswith(".") else "." + host
            cookies.append({
                "name":     name,
                "value":    value,
                "domain":   domain,
                "path":     path or "/",
                "secure":   bool(secure),
                "httpOnly": bool(http_only),
                "sameSite": "Lax",
            })
    except Exception as e:
        print(f"[!] Erreur SQLite : {e}")
    finally:
        tmp.unlink(missing_ok=True)

    if not cookies:
        print("[!] Aucun cookie Facebook trouve -- es-tu connecte dans Profile 10 ?")
        return

    SESSION_FILE.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"{len(cookies)} cookies Facebook extraits.")

    c_user = next((c["value"] for c in cookies if c["name"] == "c_user"), None)
    if c_user:
        print(f"c_user = {c_user}  (connexion confirmee)")
    else:
        print("[!] Cookie c_user absent -- verifie la connexion Facebook dans Profile 10")

    print(f"\nSession sauvegardee : {SESSION_FILE}")
    print("Prochaine etape : python tools/fb_scraper.py")


if __name__ == "__main__":
    main()
