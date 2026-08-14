import os
import re

path = r'd:\Content_Machine\machines\facebook_machine\core\routes\generation_routes.py'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Fix api_generate
old_gen = r'@router\.get\("/generate"\)\s+async def api_generate\(.*?\):\s+try:.*?thread\.start\(\)\s+return \{.*?\}'
new_gen = """@router.get("/generate")
async def api_generate(persona: str = "", topic: str = "", publish: str = "false", media: str = "none", 
                   context: str = "", objectif: str = "engagement", story: str = "", account_id: int = None):
    try:
        from core.task_tracker import create_task, update_task
        publish_bool = publish.lower() == "true"
        task_id = create_task("copywriter", message=f"Génération post: {topic[:30]}...")
        
        def run_generation():
            import sys, io
            try:
                update_task(task_id, progress=10, status="running", log="Démarrage...")
                from agents.scheduler.agent import process_single_post
                
                plan_entry = {
                    "persona": persona,
                    "sujet": topic if topic else f"Sujet automatique ({persona})",
                    "audience": "tous",
                    "context": context,
                    "objectif": objectif,
                    "story": story
                }
                date_str = datetime.now().strftime("%Y-%m-%d")
                update_task(task_id, progress=30, log="Génération du texte...")
                
                old_img_setting = Config.POST_IMAGE_ENABLED
                if media == "none":
                    Config.POST_IMAGE_ENABLED = False
                
                result = process_single_post(plan_entry, date_str, publish_bool, task_id=task_id, current=1, total=1, account_id=account_id)
                Config.POST_IMAGE_ENABLED = old_img_setting
                
                if result.success:
                    update_task(task_id, progress=100, status="completed", message="Post généré!")
                else:
                    error_msg = getattr(result, 'error_cause', 'Erreur inconnue')
                    update_task(task_id, status="failed", message=error_msg)
            except Exception as e:
                update_task(task_id, status="failed", message=str(e))
        
        thread = threading.Thread(target=run_generation, daemon=True)
        thread.start()
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "Génération du post démarrée en arrière-plan."
        }"""

content = re.sub(old_gen, new_gen, content, flags=re.DOTALL)

# Fix api_generate_reel
old_reel = r'@router\.get\("/generate_reel"\)\s+async def api_generate_reel\(.*?\):\s+try:.*?thread\.start\(\)\s+return \{.*?\}'
new_reel = """@router.get("/generate_reel")
async def api_generate_reel(topic: str = "", script: str = "", publish: str = "false", context: str = "", objectif: str = "engagement", audience: str = "freelance", account_id: int = None):
    try:
        from core.task_tracker import create_task, update_task
        publish_bool = publish.lower() == "true"
        task_id = create_task("reel", message=f"Génération reel: {topic[:30]}...")
        
        def run_reel():
            import sys, io
            try:
                update_task(task_id, progress=10, status="running", log="Démarrage...")
                from agents.scheduler.agent import process_reel
                
                date_str = datetime.now().strftime("%Y-%m-%d")
                update_task(task_id, progress=30, log="Génération du script...")
                
                reel_entry = {
                    "sujet": topic,
                    "audience": audience,
                    "context": context,
                    "objectif": objectif
                }
                
                result = process_reel(reel_entry, date_str, publish_bool, task_id=task_id, current=1, total=1, account_id=account_id)
                
                if result.success:
                    update_task(task_id, progress=100, status="completed", message="Reel généré!")
                else:
                    update_task(task_id, status="failed", message=getattr(result, 'error_cause', 'Erreur génération'))
            except Exception as e:
                update_task(task_id, status="failed", message=str(e))
        
        thread = threading.Thread(target=run_reel, daemon=True)
        thread.start()
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "Génération du reel démarrée en arrière-plan."
        }"""

content = re.sub(old_reel, new_reel, content, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Done")
