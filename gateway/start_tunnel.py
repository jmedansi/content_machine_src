#!/usr/bin/env python3
"""
Cloudflare Tunnel - Démarrage invisible avec monitoring
Support multi-services via config d'ingress
"""

import subprocess
import sys
import os
import time

# Chemin vers cloudflared et sa config
CLOUDFLARED = os.environ.get("CLOUDFLARED", "cloudflared")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".cloudflared", "config.yml")

def start_tunnel():
    """Démarre le tunnel Cloudflare en arrière-plan et le maintient"""
    CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
    
    if not os.path.exists(CONFIG_FILE):
        print(f"[ERROR] Config introuvable: {CONFIG_FILE}", file=sys.stderr)
        print("[INFO] Utilise 'cloudflared tunnel run --url http://localhost:8000 facebook-webhook' à la place", file=sys.stderr)
        return None
    
    try:
        process = subprocess.Popen(
            [CLOUDFLARED, "tunnel", "--config", CONFIG_FILE, "run"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        )
        
        # Garder le processus Python vivant pour que le dashboard puisse le surveiller
        while True:
            if process.poll() is not None:
                # cloudflared est mort, redémarrer
                print("[WARN] Tunnel mort, redémarrage...", file=sys.stderr)
                process = subprocess.Popen(
                    [CLOUDFLARED, "tunnel", "--config", CONFIG_FILE, "run"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW
                )
            time.sleep(10)
            
    except Exception as e:
        print(f"[ERROR] Erreur tunnel: {e}", file=sys.stderr)
        return None

if __name__ == "__main__":
    print(f"[INFO] Tunnel Cloudflare démarré avec config: {CONFIG_FILE} (PID: {os.getpid()})")
    start_tunnel()
