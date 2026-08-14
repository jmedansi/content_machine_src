import sys
from pathlib import Path
import json
import datetime

# Get topic from input or use default
topic = sys.argv[1] if len(sys.argv) > 1 else "Comment réussir en ligne"
audience = sys.argv[2] if len(sys.argv) > 2 else "freelance"

print(f"TOPIC: {topic}, AUDIENCE: {audience}", flush=True)

# Create folder
base = Path("D:/Content_Machine/machines/facebook-machine/content")
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
slug = topic.lower().replace(" ", "_")[:25].replace("/", "_")
folder_name = f"reel_{timestamp}_{slug}"
folder = base / folder_name
folder.mkdir(parents=True, exist_ok=True)

# Create files
(folder / "facebook_post.txt").write_text(f"Reel: {topic}", encoding="utf-8")
(folder / "reel_brief.txt").write_text(f"SUJET: {topic}\nPERSONA: {audience}", encoding="utf-8")

meta = {
    "topic": topic,
    "persona": f"reel_{audience}",
    "status": "pending",
    "has_reel": False
}
(folder / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

print(f"FOLDER_CREATED: {folder_name}", flush=True)

# Add to path and run video_maker
sys.path.insert(0, "D:/Content_Machine/machines/facebook-machine")
from shared_agents.video_maker.agent import run_video_maker

result = run_video_maker(str(folder))
print(f"RESULT_SUCCESS={result.success}", flush=True)
if result.success:
    print(f"RESULT_DATA={result.data}", flush=True)
else:
    print(f"RESULT_ERROR={result.error}", flush=True)

# Fix: renommer _raw_concat.mp4 en reel.mp4 si nécessaire
reel_dir = folder / "reel"
raw_file = reel_dir / "_raw_concat.mp4"
final_file = reel_dir / "reel.mp4"
if raw_file.exists() and not final_file.exists():
    import shutil
    shutil.copy(raw_file, final_file)
    print(f"COPIED to reel.mp4", flush=True)

if final_file.exists():
    # Update meta - utiliser les deux champs pour compatibilité
    meta["reel_generated"] = True
    meta["has_reel"] = True
    meta["status"] = "pending"  # Pour apparaître dans Validation
    meta["created_at"] = datetime.datetime.now().isoformat()
    (folder / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"SUCCESS_REEL_PATH={final_file}", flush=True)

print("DONE", flush=True)