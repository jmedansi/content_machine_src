# main.py — Point d'entrée unique pour la Facebook Machine IncidenX
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import argparse
import logging
from datetime import datetime
import json

logging.basicConfig(
    filename='errors.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s',
    encoding='utf-8'
)

def run_once(post_type="short_punch", publish=False):
    """Génère un post immédiatement (et le publie si publish=True)."""
    from agents.scheduler.agent import process_single_post

    print(f"\n[MAIN] Génération unique - Type: {post_type} - Publish: {publish}\n")
    result = process_single_post({"persona": post_type, "sujet": "Sujet manuel"}, datetime.now().strftime("%Y-%m-%d"), publish)
    return result.data if result.success else None

def run_schedule(auto_publish=False):
    """Démarre le planificateur."""
    from agents.scheduler.agent import run_pipeline
    
    print(f"\n[MAIN] Démarrage du pipeline\n")
    print(f"Publication auto: {'Oui' if auto_publish else 'Non'}\n")
    run_pipeline("all", auto_publish)

def run_publish(folder_path):
    """Publie un dossier de contenu existant."""
    from agents.publisher.agent import run_publisher
    from pathlib import Path

    folder = Path(folder_path)
    if not folder.exists():
        print(f"[ERROR] Dossier introuvable: {folder_path}")
        return None
    try:
        meta_file = folder / "meta.json"
        if meta_file.exists():
            import json as _json
            meta = _json.loads(meta_file.read_text(encoding="utf-8"))
            if meta.get("published", False):
                print(f"[WARNING] Ce contenu a déjà été publié le {meta.get('published_at', '?')}")
                response = input("Voulez-vous republier? (o/n): ")
                if response.lower() != 'o':
                    return None
    except Exception as _meta_err:
        print(f"[WARNING] meta.json illisible ({_meta_err}), poursuite de la publication.")

    print(f"\n[MAIN] Publication de: {folder.name}\n")
    result = run_publisher(folder_path)

    success = bool(getattr(result, "success", None)) if not isinstance(result, bool) else result
    if success:
        print(f"\n[SUCCESS] Post publié!")
        return {"folder": str(folder), "published": True}
    print(f"\n[ERROR] Publication échouée")
    return {"folder": str(folder), "published": False}

def list_content():
    """Liste le contenu généré."""
    from pathlib import Path
    
    content_dir = Path(__file__).parent / "content"
    if not content_dir.exists():
        print("[INFO] Aucun contenu généré")
        return []
    
    folders = sorted(content_dir.iterdir(), reverse=True)
    
    print(f"\n{'='*60}")
    print("CONTENU GÉNÉRÉ")
    print(f"{'='*60}\n")
    
    for folder in folders:
        if folder.is_dir():
            meta_file = folder / "meta.json"
            post_file = folder / "facebook_post.txt"
            
            status = "❓"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                status = "✅" if meta.get("published") else "📝"
            
            print(f"{status} {folder.name}")
            
            if post_file.exists():
                lines = post_file.read_text(encoding="utf-8").split('\n')
                print(f"   └─ {lines[0][:60]}..." if lines else "")
    
    print(f"\nTotal: {len(folders)} dossiers\n")
    return folders

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Facebook Machine IncidenX")
    
    subparsers = parser.add_subparsers(dest="command", help="Commandes")
    
    once_parser = subparsers.add_parser("once", help="Générer un post maintenant")
    once_parser.add_argument("--persona", "-p", default="expert_ia", help="Persona à utiliser")
    once_parser.add_argument("--topic", "-t", required=True, help="Sujet du post")
    once_parser.add_argument("--ressource", "-r", help="Type de ressource (pour CTA)")
    once_parser.add_argument("--publish", action="store_true", help="Publier après génération")
    
    subparsers.add_parser("schedule", help="Démarrer le planificateur")
    subparsers.add_parser("list", help="Lister le contenu généré")
    
    publish_parser = subparsers.add_parser("publish", help="Publier un dossier existant")
    publish_parser.add_argument("folder", help="Chemin du dossier à publier")
    
    args = parser.parse_args()
    
    if args.command == "once":
        from agents.scheduler.agent import process_single_post
        result = process_single_post({"persona": args.persona, "sujet": args.topic}, datetime.now().strftime("%Y-%m-%d"), args.publish)
        if result.success:
            print(f"\n[SUCCESS] Post généré (et potentiellement publié)!")
        else:
            print(f"\n[ERROR] Échec: {getattr(result, 'error_cause', 'Inconnu')}")
    elif args.command == "schedule":
        print("[SCHEDULER] Démarrage de la Facebook Machine (Scheduler)...")
        from agents.scheduler.agent import run_pipeline
        import time
        try:
            run_pipeline()
        except Exception as e:
            print(f"[SCHEDULER] Erreur lors de l'exécution initiale du pipeline: {e}")
        
        print("[SCHEDULER] Exécution initiale du pipeline terminée. En attente (veille continue)...")
        try:
            while True:
                time.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            print("[SCHEDULER] Arrêt du scheduler.")
    elif args.command == "list":
        list_content()
    elif args.command == "publish":
        run_publish(args.folder)
    else:
        parser.print_help()
        print("\n--- EXEMPLES ---")
        print("python main.py once -t 'sujet' -p expert_ia    # Générer un post")
        print("python main.py once -t 'sujet' -p cta --publish # Générer et publier")
        print("python main.py schedule                         # Démarrer le scheduler")
        print("python main.py list                             # Voir le contenu")
        print("python main.py publish content/2026-..        # Publier un dossier")
