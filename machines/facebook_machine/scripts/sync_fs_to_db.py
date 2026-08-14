import sys
import os
from pathlib import Path
import json

# Setup PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.db import init_db, SessionLocal, Account, Post
from core.config import Config

CONTENT_DIR = Config.CONTENT_DIR

def get_or_create_default_account(db):
    account = db.query(Account).filter(Account.platform == "facebook", Account.name == "Default Facebook").first()
    if not account:
        account = Account(
            platform="facebook",
            name="Default Facebook",
            credentials={"page_id": Config.FB_PAGE_ID, "access_token": Config.FB_PAGE_ACCESS_TOKEN}
        )
        db.add(account)
        db.commit()
        db.refresh(account)
    return account

def sync_folder(db, account_id, folder_path):
    meta_file = folder_path / "meta.json"
    meta = {}
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except:
            pass

    # Extract text if available
    text_files = ["facebook_post.txt", "post.txt", "content.txt"]
    text = ""
    for tf in text_files:
        p = folder_path / tf
        if p.exists():
            text = p.read_text(encoding="utf-8").strip()
            break
            
    # Check images
    has_image = meta.get("has_image", False)
    image_filename = meta.get("post_image", None)
    if not has_image:
        for img in ["post_image.jpg", "post_image.webp", "image.jpg", "image.png"]:
            if (folder_path / img).exists():
                has_image = True
                image_filename = img
                break

    # Check reel
    has_reel = meta.get("has_reel", False)
    reel_filename = meta.get("reel_file", None)
    if not has_reel:
        for r in ["reel/reel.mp4", "reel/video.mp4", "video.mp4"]:
            if (folder_path / r).exists():
                has_reel = True
                reel_filename = r
                break

    # Determine status
    status = meta.get("status")
    if not status:
        if meta.get("published", False):
            status = "published"
        elif meta_file.exists():
            status = "pending"
        else:
            status = "corrupted"

    # Create or update Post
    post = db.query(Post).filter(Post.folder_name == folder_path.name).first()
    if not post:
        post = Post(folder_name=folder_path.name, account_id=account_id)
        db.add(post)
    
    post.persona = meta.get("persona", "?")
    topic_data = meta.get("topic", "")
    if isinstance(topic_data, dict):
        topic_data = json.dumps(topic_data, ensure_ascii=False)
    post.topic = topic_data
    post.content_text = text
    post.status = status
    post.published = status == "published" or meta.get("published", False)
    post.scheduled_time = meta.get("scheduled_time", "")
    post.has_image = has_image
    post.image_filename = image_filename
    post.image_failed = meta.get("image_failed", False)
    post.has_reel = has_reel
    post.reel_filename = reel_filename
    post.llm_provider = meta.get("llm_provider", "")
    post.llm_model = meta.get("llm_model", "")
    
    db.commit()
    print(f"[SYNC] Synced folder: {folder_path.name} (Status: {status})")

def main():
    print("Initialisation de la base de données...")
    init_db()
    db = SessionLocal()
    
    try:
        account = get_or_create_default_account(db)
        print(f"Compte par défaut : {account.name} (ID: {account.id})")
        
        if not CONTENT_DIR.exists():
            print("Dossier content introuvable.")
            return

        folders = sorted([f for f in CONTENT_DIR.iterdir() if f.is_dir()])
        for folder in folders:
            sync_folder(db, account.id, folder)
            
        print("Synchronisation terminée avec succès.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
