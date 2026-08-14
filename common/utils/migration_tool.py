# migration_tool.py — Migration des dossiers racine vers acc_N
# Usage: python migration_tool.py

import json
import shutil
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent.parent

PLATFORMS = {
    "facebook": BASE / "machines" / "facebook_machine",
    "linkedin": BASE / "machines" / "linkedin_machine",
    "twitter": BASE / "machines" / "twitter_machine",
}


def migrate_platform(platform: str, dry_run: bool = True):
    """Migre les dossiers racine vers acc_{id}/ pour une plateforme."""
    plat_dir = PLATFORMS.get(platform)
    if not plat_dir:
        print(f"Plateforme introuvable: {platform}")
        return
    
    print(f"\n=== Migration {platform} ===")
    
    # 1. Migrer persona/
    persona_src = plat_dir / "persona"
    # On ne migre pas persona src vers acc_1 car ça devient le default
    # Les nouveaux comptes utiliseront les personas par défaut
    
    # 2. Migrer content/ (optionnel - vers accounts/1)
    content_src = plat_dir / "content"
    if content_src.exists() and not dry_run:
        acc1_content = plat_dir / "accounts" / "1" / "content"
        if not acc1_content.exists():
            acc1_content.mkdir(parents=True, exist_ok=True)
        
        # Copier tous les contenu vers accounts/1/content
        for item in content_src.iterdir():
            dest = acc1_content / item.name
            if not dest.exists():
                shutil.copytree(item, dest)
                print(f"  Copié: {item.name} -> accounts/1/content/")
    
    # 3. Créer schedule.json pour chaque account existant (sous accounts/)
    if not dry_run:
        accounts_root = plat_dir / "accounts"
        if accounts_root.exists():
            for acc_dir in accounts_root.iterdir():
                if not acc_dir.is_dir():
                    continue
                schedule_file = acc_dir / "schedule.json"
                if not schedule_file.exists():
                    schedule_file.write_text(json.dumps({"schedule": []}), encoding="utf-8")
                    print(f"  Créé: {schedule_file}")
    
    print(f"{'[DRY RUN] ' if dry_run else ''}Migration {platform} terminée")


def create_account(platform: str, name: str) -> int:
    """Crée un nouveau compte avec ses dossiers."""
    plat_dir = PLATFORMS.get(platform)
    if not plat_dir:
        raise ValueError(f"Plateforme introuvable: {platform}")
    # Trouver le prochain ID dans accounts/
    accounts_root = plat_dir / "accounts"
    accounts_root.mkdir(parents=True, exist_ok=True)
    max_id = 0
    for acc_dir in accounts_root.iterdir():
        if acc_dir.is_dir():
            try:
                acc_id = int(acc_dir.name)
                max_id = max(max_id, acc_id)
            except Exception:
                pass

    new_id = max_id + 1
    acc_dir = accounts_root / str(new_id)
    acc_dir.mkdir(parents=True, exist_ok=True)
    (acc_dir / "persona").mkdir(exist_ok=True)
    (acc_dir / "content").mkdir(parents=True, exist_ok=True)
    (acc_dir / "schedule.json").write_text(json.dumps({"schedule": []}), encoding="utf-8")
    (acc_dir / "meta.json").write_text(json.dumps({
        "name": name,
        "platform": platform,
        "created": datetime.now().isoformat()
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Compte {new_id} créé: {acc_dir}")
    return new_id


def list_accounts(platform: str = None):
    """Liste tous les comptes."""
    for p, plat_dir in PLATFORMS.items():
        if platform and platform != p:
            continue
        
        print(f"\n=== {p.upper()} ===")
        print(f"  Racine: {plat_dir}")
        print(f"  (Default personas: {(plat_dir / 'persona').exists()})")
        
        # Trouver les accounts (sous accounts/)
        accounts = []
        accounts_root = plat_dir / "accounts"
        if accounts_root.exists():
            for acc_dir in sorted(accounts_root.iterdir()):
                if not acc_dir.is_dir():
                    continue
                try:
                    account_id = int(acc_dir.name)
                    accounts.append((account_id, acc_dir))
                except Exception:
                    continue
        
        if not accounts:
            print(" Aucun account créé")
            continue
        
        for account_id, acc_dir in sorted(accounts):
            # Lire meta
            meta = {}
            meta_file = acc_dir / "meta.json"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            
            # Compter contenu
            content_dir = acc_dir / "content"
            n_content = len(list(content_dir.iterdir())) if content_dir.exists() else 0
            
            # Compter personas
            persona_dir = acc_dir / "persona"
            n_persona = len(list(persona_dir.iterdir())) if persona_dir.exists() else 0
            
            print(f"  {account_id}: {meta.get('name', 'Sans nom')} - {n_content} posts, {n_persona} personas")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "list":
            list_accounts()
        elif cmd == "dry-run":
            for p in ["facebook", "linkedin", "twitter"]:
                migrate_platform(p, dry_run=True)
        elif cmd == "migrate":
            for p in ["facebook", "linkedin", "twitter"]:
                migrate_platform(p, dry_run=False)
        elif cmd == "create":
            platform = sys.argv[2] if len(sys.argv) > 2 else "facebook"
            name = sys.argv[3] if len(sys.argv) > 3 else "Nouveau compte"
            create_account(platform, name)
        else:
            print("Usage: python migration_tool.py [list|dry-run|migrate|create <platform> <name>]")
    else:
        print("Usage: python migration_tool.py [list|dry-run|migrate|create <platform> <name>]")
        print("\nCommands:")
        print("  list         - Liste tous les comptes")
        print("  dry-run      - Simule la migration")
        print("  migrate     - Execute la migration")
        print("  create       - Crée un nouveau compte")