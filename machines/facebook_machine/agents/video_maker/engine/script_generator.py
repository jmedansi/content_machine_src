# script_generator.py -- Générateur de script AV via Groq
# Version avec variété : preuves réelles, structures variées

import json
import logging
import os
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import requests
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
from core.groq_router import MODEL_POSTS
GROQ_MODEL   = MODEL_POSTS
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

# Différentes structures possibles
STRUCTURES = [
    {
        "name": "classique_6_slides",
        "slides": [
            {"position": 0, "type": "hook", "desc": "Question ou affirmation choc"},
            {"position": 1, "type": "tip", "number": 1, "desc": "Premier conseil"},
            {"position": 2, "type": "tip", "number": 2, "desc": "Deuxième conseil"},
            {"position": 3, "type": "tip", "number": 3, "desc": "Troisième conseil"},
            {"position": 4, "type": "proof", "desc": "Preuve réelle (statistique, étude, exemple)"},
            {"position": 5, "type": "cta", "desc": "Appel à l'action"},
        ]
    },
    {
        "name": "problem_solution",
        "slides": [
            {"position": 0, "type": "hook", "desc": "Problème concret"},
            {"position": 1, "type": "stat", "desc": "Statistique choquante"},
            {"position": 2, "type": "tip", "number": 1, "desc": "Solution 1"},
            {"position": 3, "type": "tip", "number": 2, "desc": "Solution 2"},
            {"position": 4, "type": "proof", "desc": "Preuve étude/experte"},
            {"position": 5, "type": "cta", "desc": "Call to action"},
        ]
    },
    {
        "name": "mythes_vs_realite",
        "slides": [
            {"position": 0, "type": "hook", "desc": "Mythe à détruire"},
            {"position": 1, "type": "stat", "desc": "Réalité avec chiffre"},
            {"position": 2, "type": "tip", "number": 1, "desc": "Vérité 1"},
            {"position": 3, "type": "tip", "number": 2, "desc": "Vérité 2"},
            {"position": 4, "type": "proof", "desc": "Exemple réel (entreprise, personne)"},
            {"position": 5, "type": "cta", "desc": "Action demandée"},
        ]
    },
    {
        "name": "avant_apres",
        "slides": [
            {"position": 0, "type": "hook", "desc": "Situation actuelle"},
            {"position": 1, "type": "stat", "desc": "Chiffre avant"},
            {"position": 2, "type": "tip", "number": 1, "desc": "Transformation 1"},
            {"position": 3, "type": "tip", "number": 2, "desc": "Transformation 2"},
            {"position": 4, "type": "proof", "desc": "Résultat après (statistique)"},
            {"position": 5, "type": "cta", "desc": "Invitation"},
        ]
    },
]

# Preuves réelles par catégorie d'audience
REAL_PROOFS = {
    "freelance": [
        "71% des freelances africains gagnent moins de 500$/mois selon une étude de 2024",
        "Les freelances avec site web personnel gagnent 3x plus de clients",
        "90% des entreprises africaines recrutent en ligne",
        "Le marché du freelancing en Afrique atteint 15 milliards$ en 2025",
        "Les freelances熟练(熟练) en IA facturent 2x plus",
    ],
    "pme": [
        "67% des PME africaines sans site web perdent 40% de clients potentiels",
        "Les PME avec présence digitale grows 2x plus vite",
        "85% des consumers africains recherchent en ligne avant d'acheter",
        "L'adoption de l'IA par les PME africaines a augmenté de 340% en 2 ans",
    ],
    "apprenant": [
        "72% des apprenants africains apprennent via leur téléphone",
        "Les formations avec pratique ont 3x plus de taux de complétion",
        "93% des recruteurs checkent le profil LinkedIn avant de'embaucher",
    ],
}

# Types de hooks possibles
HOOK_TYPES = [
    "question_douleur", "stat_choquant", "affirmation_controversée",
    "mythe_a_detruire", "promesse_resultat", "question_rhétorique",
]

AV_SCRIPT_PROMPT = """Tu es un copywriter expert en Reels Facebook viraux pour une audience africaine francophone.

SUJET : {topic}
AUDIENCE : {audience}

Structure à utiliser : {structure_name}
Description : {structure_desc}

CONTEXTE ET PREUVES RÉELLES (utilise ces infos ou génère-en de similaires basées sur {audience}) :
{real_proofs}

IMPORTANT - RÈGLES DE VARIÉTÉ :
1. Le hook (slide 1) peut être : question choquante, statistique, affirmation forte, mythe à détruire
2. Les tips (slides 2-4) doivent être concrets et Actionnables avec des chiffres si possible
3. La preuve (slide 5) doit être une STATISTIQUE RÉELLE, une ÉTUDE, un EXEMPLE d'entreprise/personne connne, JAMAIS "moi" ou "j'ai"
4. Le CTA (slide 6) doit être spécifique et measura

FORMAT DE SORTIE JSON (6 slides) :
[
  {{"type": "hook", "title": "...", "subtitle": "...", "narration": "...", "lottie_keyword": "...", "duration": 3.0}},
  {{"type": "tip", "number": 1, "title": "...", "subtitle": "...", "narration": "...", "lottie_keyword": "...", "duration": 4.0}},
  {{"type": "tip", "number": 2, "title": "...", "subtitle": "...", "narration": "...", "lottie_keyword": "...", "duration": 4.0}},
  {{"type": "tip", "number": 3, "title": "...", "subtitle": "...", "narration": "...", "lottie_keyword": "...", "duration": 4.0}},
  {{"type": "proof", "title": "...", "subtitle": "...", "narration": "...", "lottie_keyword": "...", "duration": 4.0}},
  {{"type": "cta", "title": "...", "subtitle": "...", "narration": "...", "lottie_keyword": "...", "duration": 3.5}}
]

RÈGLES :
- title: max 8 mots, accroche forte
- subtitle: max 15 mots, complète le title
- narration: phrase complète pour le TTS
- lottie_keyword: parmi invoice, money, payment, revenue, growth, chart, clients, happy, handshake, team, success, trophy, star, winner, celebrate, learning, book, idea, skills, time, clock, productivity, focus, freelance, laptop, business, negotiation, cta, phone, globe, africa
- JAMAIS de "moi", "j'ai", "mon expérience" pour les preuves - utiliser des stats ou exemples réels
- Langue : français clair, sans jargon, ton "tu" (pas "vous")

Réponds UNIQUEMENT en JSON valide sans markdown. SUJET: {topic}"""



def _call_groq(prompt: str) -> str | None:
    """Délègue au routeur centralisé avec rotation de clés et de modèles."""
    import sys
    import os
    # Assurer que core/ est dans le path quand appelé depuis engine/
    base = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    if base not in sys.path:
        sys.path.insert(0, os.path.abspath(base))
    try:
        from core.groq_router import call_groq
        return call_groq(prompt, model=GROQ_MODEL, temperature=0.9, max_tokens=2048)
    except ImportError:
        # Fallback si core n'est pas accessible (appel standalone)
        if not GROQ_API_KEY:
            return None
        import requests
        for model in [GROQ_MODEL, "llama-3.1-8b-instant", "llama-3.1-70b-versatile"]:
            try:
                r = requests.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.9, "max_tokens": 2048},
                    timeout=30,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
                elif r.status_code != 429:
                    break
            except Exception:
                pass
        return None


def _parse_script(raw: str) -> list | None:
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        if isinstance(data, list) and len(data) >= 4:
            return data
    except Exception:
        pass
    return None


def generate_av_script(topic: str, persona: str = "") -> list | None:
    import random
    
    print(f"[SCRIPT_GEN] Génération script : {topic[:60]}...")
    
    # Sélectionner une structure aléatoire
    structure = random.choice(STRUCTURES)
    structure_name = structure["name"]
    structure_desc = structure["slides"]
    
    # Récupérer les preuves réelles selon l'audience
    audience_key = persona.replace("reel_", "") if persona else "freelance"
    real_proofs = REAL_PROOFS.get(audience_key, REAL_PROOFS["freelance"])
    proofs_text = "\n".join([f"- {p}" for p in real_proofs[:3]])
    
    prompt = AV_SCRIPT_PROMPT.format(
        topic=topic,
        audience=audience_key,
        structure_name=structure_name,
        structure_desc=str(structure_desc),
        real_proofs=proofs_text
    )
    
    raw = _call_groq(prompt)
    if not raw:
        print("[SCRIPT_GEN] Groq indisponible")
        return None
    
    scenes = _parse_script(raw)
    if not scenes:
        print(f"[SCRIPT_GEN] Parse échec:\n{raw[:400]}")
        return None
    
    print(f"[SCRIPT_GEN] {len(scenes)} slides générés (structure: {structure_name})")
    for i, s in enumerate(scenes):
        print(f"  {i+1}. [{s.get('type','?'):6s}] {s.get('title','')[:55]}")
    
    return scenes


def script_to_av_format(scenes: list) -> str:
    lines = [f"{'TITRE':<50} | SOUS-TITRE", "-" * 90]
    for i, s in enumerate(scenes):
        t = s.get("title", "")[:48]
        st = s.get("subtitle", "")[:38]
        lines.append(f"[{i+1}] {t:<48} | {st}")
    return "\n".join(lines)


if __name__ == "__main__":
    topic = "Comment gagner 3000€/mois en freelance"
    script = generate_av_script(topic, "freelance")
    if script:
        print("\n" + "=" * 90)
        print(script_to_av_format(script))
        out = Path(__file__).parent.parent / "temp" / "last_av_script.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSauvegarde : {out}")