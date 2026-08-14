# webhook_server.py — Point d'entrée principal (délègue à webhook_monitor/agent.py)
# Recrée après suppression accidentelle du .py (le .pyc était encore en cache).
import sys
import os
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "dashboard"))
sys.path.insert(0, os.path.join(ROOT_DIR, "gateway"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webhook_monitor.agent import app

if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser(description="Facebook Webhook Server")
    parser.add_argument("--poll", action="store_true", help="Mode polling")
    parser.add_argument("--port", type=int, default=8000, help="Port du serveur")
    args = parser.parse_args()

    if args.poll:
        from webhook_monitor.agent import poll_comments
        poll_comments()
    else:
        print(f"[INFO] Serveur webhook sur http://0.0.0.0:{args.port}")
        uvicorn.run(app, host="0.0.0.0", port=args.port)
