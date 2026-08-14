from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
import uvicorn
import shutil
import os
import asyncio
import webbrowser
from threading import Timer
from pathlib import Path
from gemini_engine import GeminiEngine
from watermark_tool import erase_gemini_watermark

app = FastAPI()
engine = GeminiEngine()

# Dossier d'upload
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Servir les fichiers statiques (Dashboard)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.post("/api/generate")
async def generate_image(prompt: str = Form(...)):
    print(f"[API] Génération demandée : {prompt}")
    try:
        result = await engine.run(prompt, mode="generate")
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/modify")
async def modify_image(prompt: str = Form(...), file: UploadFile = File(...)):
    print(f"[API] Modification demandée : {prompt} (image: {file.filename})")
    try:
        # 1. Sauvegarde locale temporaire de l'image à modifier
        temp_path = UPLOAD_DIR / file.filename
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 2. Lancement du moteur Playwright
        result = await engine.run(prompt, local_image=str(temp_path.absolute()), mode="modify")
        
        # Nettoyage fichier temporaire
        # os.remove(temp_path)
        
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/clean")
async def clean_image(file: UploadFile = File(...)):
    print(f"[API] Nettoyage simple demandé : {file.filename}")
    try:
        temp_path = UPLOAD_DIR / f"manual_clean_{file.filename}"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        if erase_gemini_watermark(str(temp_path.absolute())):
            return {"status": "success", "message": "Image nettoyée avec succès dans le dossier uploads."}
        else:
            return JSONResponse(status_code=500, content={"error": "Le nettoyage a échoué."})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    # Ouvrir automatiquement le dashboard après un court délai pour laisser au serveur le temps de démarrer
    Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run(app, host="127.0.0.1", port=8000)
