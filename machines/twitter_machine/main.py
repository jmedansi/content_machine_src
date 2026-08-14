#!/usr/bin/env python3
# main.py — Point d'entrée Twitter (orchestration complète)
import sys
import io
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Forcer l'encodage UTF-8 pour le terminal Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import config_manager
from agents.agent_topics import generate_topics
from agents.agent_writer import write_validated_topics, generate_tweet
from agents.agent_publisher import post_twitter
from agents.scheduler.agent import process_single_tweet, run_pipeline, publish_pending_tweets

# Configuration du logging
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s:%(levelname)s:%(message)s',
    encoding='utf-8'
)


def get_account_id_from_db():
    """Cherche le premier compte Twitter actif en DB."""
    try:
        sys.path.insert(0, "D:/Content_Machine/machines/facebook_machine")
        from core.db import SessionLocal, Account
        
        db = SessionLocal()
        try:
            account = db.query(Account).filter(
                Account.platform == "twitter",
                Account.status == "active"
            ).first()
            if account:
                return account.id
        finally:
            db.close()
    except Exception:
        pass
    
    return 1


def run_generate(account_id=1):
    """Étape 1 — Générer les sujets pour un compte"""
    if not config_manager.validate_config():
        return
    
    print(f"\n🚀 Génération des sujets - Compte {account_id}\n")
    generate_topics(n=10, account_id=account_id)
    print(f"\n👉 Prochaine étape:")
    print(f"   - Validez les sujets dans: accounts/{account_id}/data/topics_pending.json")
    print(f"   - Lancez la rédaction: python main.py write -a {account_id}")


def run_write(account_id=1):
    """Étape 2 — Rédiger les sujets validés d'un compte"""
    if not config_manager.validate_config():
        return
    
    print(f"\n🚀 Rédaction des sujets validés - Compte {account_id}\n")
    
    # Chercher les topics validés
    try:
        topics_path = Path("accounts") / str(account_id) / "data" / "topics_pending.json"
        if not topics_path.exists():
            topics_path = Path("data") / "topics_pending.json"
        
        if not topics_path.exists():
            print(f"⚠️ Aucun sujet trouvé.")
            print(f"👉 Lancez d'abord: python main.py generate -a {account_id}")
            return
        
        folders = write_validated_topics(account_id=account_id)
        
        if not folders:
            print(f"⚠️ Aucun sujet validé.")
            print(f"👉 Validez les sujets dans: accounts/{account_id}/data/topics_pending.json")
            return
        
        print(f"\n✅ {len(folders)} tweet(s) rédigé(s) pour le compte {account_id}.")
        print(f"👉 Prochaine étape: python main.py publish -a {account_id}")
        
    except Exception as e:
        logging.error(f"Erreur write: {e}")
        print(f"❌ Erreur: {e}")


def run_publish(account_id=1):
    """Étape 3 — Publier les tweets rédigés non publiés d'un compte"""
    if not config_manager.validate_config():
        return

    print(f"\n🚀 Publication des tweets - Compte {account_id}\n")
    content_dir = Path("accounts") / str(account_id) / "content"
    if not content_dir.exists():
        print(f"⚠️ Aucun dossier 'accounts/{account_id}/content/' trouvé.")
        return

    # Chercher tous les dossiers avec published: false
    folders_to_publish = []
    for folder in content_dir.iterdir():
        if folder.is_dir():
            meta_path = folder / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    if not meta.get("published", False):
                        folders_to_publish.append(folder)
                except Exception:
                    continue

    if not folders_to_publish:
        print(f"ℹ️ Aucun tweet en attente de publication.")
        return

    print(f"📦 {len(folders_to_publish)} tweet(s) trouvé(s).\n")

    for folder in folders_to_publish:
        try:
            meta_path = folder / "meta.json"
            if not meta_path.exists():
                continue
            meta = json.loads(meta_path.read_text(encoding="utf-8"))

            print(f"📤 Publication : {meta.get('titre', folder.name)}")
            success = post_twitter(str(folder), account_id=account_id)

            if success:
                meta["published"] = True
                meta["published_at"] = datetime.now().isoformat()
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"✅ Publié!\n")
            else:
                print(f"⚠️ Échec de la publication\n")
                
        except Exception as e:
            logging.error(f"Erreur publication: {e}")
            print(f"❌ Erreur : {e}\n")

    print(f"🎉 Terminé.\n")


def run_orchestrated(account_id=1, topics_count=5, publish=False):
    """Lance la pipeline complète orchestrée (comme Facebook).
    
    Génère → Rédige → Publie (optionnel) en une seule commande.
    """
    if not config_manager.validate_config():
        return
    
    print(f"\n{'='*60}")
    print(f"🐦 Pipeline Twitter Orchestrée")
    print(f"   Compte: {account_id}")
    print(f"   Topics: {topics_count}")
    print(f"   Auto-Publication: {'Oui' if publish else 'Non'}")
    print(f"{'='*60}\n")
    
    # 1. Générer les topics
    print(f"1️⃣  Génération des sujets...")
    generate_topics(n=topics_count, account_id=account_id)
    
    # 2. Charger et traiter
    try:
        topics_path = Path("accounts") / str(account_id) / "data" / "topics_pending.json"
        if not topics_path.exists():
            topics_path = Path("data") / "topics_pending.json"
        
        if not topics_path.exists():
            print(f"❌ Aucun topic généré")
            return
        
        data = json.loads(topics_path.read_text(encoding="utf-8"))
        topics = data.get("topics", [])
        if isinstance(topics, dict):
            topics = [topics]
        
        # Valider tous les topics pour mode orchestré
        for topic in topics:
            topic["validated"] = True
        
        # Rédiger et éventuellement publier
        print(f"\n2️⃣  Rédaction et publication...")
        results = run_pipeline(account_id, topics=topics, publish=publish)
        
        success_count = sum(1 for r in results if r.success)
        published_count = sum(1 for r in results if r.published)
        
        print(f"\n{'='*60}")
        print(f"✅ Pipeline terminée")
        print(f"   Tweets générés: {success_count}")
        print(f"   Tweets publiés: {published_count}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        logging.error(f"Erreur pipeline: {e}")
        print(f"❌ Erreur: {e}")


def main():
    """Point d'entrée principal avec CLI amélioré."""
    parser = argparse.ArgumentParser(
        description="Twitter Machine - Génération & Publication de tweets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python main.py generate -a 1           # Générer topics pour compte 1
  python main.py write -a 1              # Rédiger tweets validés
  python main.py publish -a 1            # Publier tweets en attente
  python main.py orchestrated -a 1 -p    # Pipeline complète avec publication
        """
    )
    
    parser.add_argument(
        'command',
        nargs='?',
        default='generate',
        choices=['generate', 'write', 'publish', 'orchestrated', 'list'],
        help='Commande à exécuter'
    )
    
    parser.add_argument(
        '-a', '--account',
        type=int,
        default=None,
        dest='account_id',
        help='ID du compte Twitter (défaut: 1 ou premier compte DB)'
    )
    
    parser.add_argument(
        '-t', '--topics',
        type=int,
        default=5,
        help='Nombre de topics à générer (défaut: 5)'
    )
    
    parser.add_argument(
        '-p', '--publish',
        action='store_true',
        help='Publier automatiquement (pour mode orchestrated)'
    )
    
    try:
        args = parser.parse_args()
        
        # Déterminer account_id
        account_id = args.account_id
        if not account_id:
            account_id = get_account_id_from_db()
            if account_id == 1:
                print(f"ℹ️ Utilisation du compte par défaut: {account_id}")
        
        # Exécuter la commande
        if args.command == 'generate':
            run_generate(account_id)
        elif args.command == 'write':
            run_write(account_id)
        elif args.command == 'publish':
            run_publish(account_id)
        elif args.command == 'orchestrated':
            run_orchestrated(account_id, topics_count=args.topics, publish=args.publish)
        elif args.command == 'list':
            print(f"📋 Tweets du compte {account_id}:")
            content_dir = Path("accounts") / str(account_id) / "content"
            if content_dir.exists():
                for folder in sorted(content_dir.iterdir(), reverse=True):
                    if folder.is_dir():
                        meta_path = folder / "meta.json"
                        if meta_path.exists():
                            meta = json.loads(meta_path.read_text(encoding="utf-8"))
                            status = "✅" if meta.get("published") else "📝"
                            print(f"  {status} {folder.name}")
            else:
                print(f"  ⚠️ Aucun contenu")
        
    except KeyboardInterrupt:
        print("\n👋 Arrêt demandé par l'utilisateur.")
    except Exception as e:
        logging.error(f"Erreur critique: {e}")
        print(f"❌ Erreur critique: {e}")


if __name__ == "__main__":
    main()
