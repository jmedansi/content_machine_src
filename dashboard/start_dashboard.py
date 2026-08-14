#!/usr/bin/env python3
"""
start_dashboard.py — Script moderne pour démarrer le dashboard Content Machine

Usage:
    python start_dashboard.py [--port PORT] [--host HOST] [--reload]

Options:
    --port PORT     Port du serveur (défaut: 8000)
    --host HOST     Host du serveur (défaut: 127.0.0.1)
    --reload        Rechargement automatique en développement
    --background    Démarrage en arrière-plan (détaché)
"""

import sys
import os
import subprocess
import time
import argparse
import signal
import socket
from pathlib import Path

# Configuration des chemins
ROOT_DIR = Path(__file__).parent.parent
DASHBOARD_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(DASHBOARD_DIR))

def is_port_open(host, port):
    """Vérifie si un port est déjà utilisé"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        return result == 0

def kill_existing_processes(port=8000):
    """Tue les processus Python existants sur le port cible"""
    try:
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            shell=False
        )
        stdout = result.stdout or ""

        for line in stdout.splitlines():
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    try:
                        subprocess.run(['taskkill', '/F', '/PID', pid], check=True)
                        print(f"✓ Processus {pid} arrêté")
                    except subprocess.CalledProcessError:
                        pass
    except Exception as e:
        print(f"⚠ Impossible d'arrêter les processus existants: {e}")

def start_dashboard(host='127.0.0.1', port=8000, reload=False, background=False):
    """Démarre le dashboard"""
    print("=" * 60)
    print("🚀 IncidenX Content Machine Dashboard")
    print("=" * 60)

    # Vérification du port
    if is_port_open(host, port):
        print(f"⚠ Port {port} déjà utilisé. Arrêt des processus existants...")
        kill_existing_processes(port)
        time.sleep(2)

    # Commande de démarrage
    cmd = [
        sys.executable,
        str(DASHBOARD_DIR / "dashboard_api_v2.py"),
        "--port", str(port)
    ]

    if background:
        print(f"📍 Démarrage en arrière-plan sur http://{host}:{port}")
        # Démarrage détaché sur Windows
        subprocess.Popen(
            cmd,
            cwd=str(DASHBOARD_DIR),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        print(f"📍 Démarrage sur http://{host}:{port}")
        print("📍 Appuyez sur Ctrl+C pour arrêter")
        print()

        try:
            subprocess.run(cmd, cwd=str(DASHBOARD_DIR), check=True)
        except KeyboardInterrupt:
            print("\n🛑 Arrêt du serveur...")
        except subprocess.CalledProcessError as e:
            print(f"❌ Erreur lors du démarrage: {e}")
            return False

    # Vérification du démarrage
    print("⏳ Vérification du démarrage...")
    for i in range(10):
        if is_port_open(host, port):
            print("✅ Dashboard démarré avec succès!")
            print(f"🌐 URL: http://{host}:{port}")
            print(f"📊 API: http://{host}:{port}/docs")
            print("=" * 60)
            return True
        time.sleep(1)

    print("❌ Le serveur n'a pas démarré correctement")
    return False

def main():
    parser = argparse.ArgumentParser(
        description="Démarreur du Dashboard Content Machine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python start_dashboard.py                    # Démarrage normal
  python start_dashboard.py --port 3000       # Port personnalisé
  python start_dashboard.py --background      # Démarrage en arrière-plan
  python start_dashboard.py --reload          # Mode développement
        """
    )

    parser.add_argument('--host', default='127.0.0.1',
                       help='Host du serveur (défaut: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8000,
                       help='Port du serveur (défaut: 8000)')
    parser.add_argument('--reload', action='store_true',
                       help='Rechargement automatique en développement')
    parser.add_argument('--background', action='store_true',
                       help='Démarrage en arrière-plan (détaché)')

    args = parser.parse_args()

    # Gestion du signal Ctrl+C
    def signal_handler(sig, frame):
        print("\n🛑 Arrêt demandé par l'utilisateur...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Démarrage
    success = start_dashboard(
        host=args.host,
        port=args.port,
        reload=args.reload,
        background=args.background
    )

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()