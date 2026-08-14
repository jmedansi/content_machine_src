import os
import json
import requests
import logging
from pathlib import Path
from dotenv import load_dotenv

# Charger les variables d'env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# Configuration du logging
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

SYSTEM_PROMPT = """Tu es un expert en copywriting LinkedIn spécialisé dans les carousels à haute rétention (Style Canva Premium).
Ton objectif est de transformer un sujet complexe en une série de slides infographiques percutants.

Structure du Carousel (7 slides) :
1. Slide 1 (intro) : Titre Massif (Hook). Doit arrêter le scroll.
2. Slide 2-6 (step) : Un point clé sous forme "Titre : Description Courte".
3. Slide 7 (cta) : Conclusion et appel à l'action.

Règles de style "Pro Max" :
- Titres très courts (max 5-7 mots).
- Chaque slide 'step' DOIT suivre le format "NOM DE L'ÉTAPE : Explication en une phrase".
- Utilise les 'visualType' suivants : 'intro', 'step', 'result', 'cta'.
- Pas de jargon, ton d'expert B2B accessible.

Format de sortie attendu (JSON uniquement) :
{
  "title": "Titre global",
  "slides": [
    {"text": "TITRE HOOK : Sous-titre rapide", "visualType": "intro"},
    {"text": "L'AUTOMATISATION : Pourquoi c'est vital pour votre PME.", "visualType": "step"},
    ...
    {"text": "CONCLUSION : Prêt à passer le cap ?", "visualType": "cta"}
  ]
}"""

def generate_with_groq(system_prompt, user_prompt):
    """Génération via Groq (Fallback)."""
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        logging.error("Groq non disponible pour le fallback.")
        return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Erreur Groq: {e}")
        return None

def generate_carousel_content(topic):
    """Génère le contenu du carousel. Tente Ollama, puis Groq en fallback."""
    prompt = f"Sujet : {topic}\n\nGénère un carousel de 7 slides B2B impactant pour LinkedIn."
    
    # --- TENTATIVE OLLAMA ---
    print("[INFO] Tentative avec Ollama (DeepSeek)...")
    try:
        url = f"{OLLAMA_URL}/api/generate"
        payload = {
            "model": "deepseek-v3.2:cloud",
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return json.loads(response.json().get("response", "{}"))
    except Exception as e:
        print(f"[WARNING] Ollama indisponible ({e}).")

    # --- TENTATIVE GROQ ---
    if GROQ_AVAILABLE and GROQ_API_KEY:
        print("[INFO] Fallback sur Groq API...")
        content = generate_with_groq(SYSTEM_PROMPT, prompt)
        if content:
            return json.loads(content)
    
    return None

if __name__ == "__main__":
    import sys
    test_topic = "Les 3 erreurs fatales de l'automatisation en PME"
    if len(sys.argv) > 1:
        test_topic = sys.argv[1]
    
    result = generate_carousel_content(test_topic)
    if result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("❌ Échec de génération (Ollama & Groq).")
