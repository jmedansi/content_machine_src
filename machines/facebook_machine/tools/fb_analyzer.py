# fb_analyzer.py — Analyse les posts scrapes et genere les fichiers persona
# Usage : python tools/fb_analyzer.py
# Prerequis : avoir tourne fb_scraper.py
# Resultat : personas/cerveau_<slug>/system_prompt.md + examples.md + config.json

import json
import os
import re
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
from core.groq_router import MODEL_POSTS
GROQ_MODEL   = MODEL_POSTS
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

SCRAPED_DIR  = Path(__file__).parent / "scraped"
PERSONAS_DIR = Path(__file__).parent.parent / "personas"

# ── Contexte de Jean-Marc pour adapter chaque persona a son objectif ─────────
JM_CONTEXT = """
Jean-Marc DANSI — marque personnelle francophone, audience africaine.
Objectif : apparaitre comme une personne interessante, credible et attachante.
Sujets : IA, developpement, business, culture, humour, storytelling personnel.
Ton cible : direct, chaleureux, "tu" jamais "vous", pas de jargon.
Format principal : Reels Facebook (hook court + details en commentaire).
"""

ANALYSIS_PROMPT = """Tu es un expert en copywriting et analyse de contenu Facebook.

Voici {n} posts publics de la page "{slug}" sur Facebook.
Cette page publie du contenu sur : {niche}.

--- POSTS ---
{posts_sample}
--- FIN POSTS ---

CONTEXTE D'APPLICATION :
{jm_context}

Analyse ce corpus et produis un rapport JSON avec EXACTEMENT cette structure :

{{
  "nom_persona": "nom court du persona (ex: 'Le Declencheur IA')",
  "niche": "description 1 phrase de ce que cette page fait",
  "signature_hooks": [
    "formule d'accroche type 1 (ex: 'Chiffre + affirmation choc')",
    "formule d'accroche type 2",
    "formule d'accroche type 3"
  ],
  "structure_posts": [
    "schema narratif 1 (ex: 'Trigger court 1-2 lignes -> details en commentaire')",
    "schema narratif 2",
    "schema narratif 3"
  ],
  "ton_vocabulaire": {{
    "registre": "ex: populaire / intellectuel / technique / storytelling",
    "expressions_signature": ["expression 1", "expression 2", "expression 3"],
    "ce_qu_il_evite": ["ce qu'il n'ecrit jamais 1", "2", "3"]
  }},
  "patterns_engagement": {{
    "cta_types": ["type de CTA 1", "type de CTA 2"],
    "questions_types": ["type de question posee 1", "type 2"],
    "commentaire_strategy": "description de la strategie commentaire (ex: 'thread avec les details')"
  }},
  "sujets_angles": [
    "angle sujet 1",
    "angle sujet 2",
    "angle sujet 3",
    "angle sujet 4"
  ],
  "exemples_hooks_adaptes_jm": [
    "hook adapte au contexte JM exemple 1",
    "hook adapte au contexte JM exemple 2",
    "hook adapte au contexte JM exemple 3",
    "hook adapte au contexte JM exemple 4",
    "hook adapte au contexte JM exemple 5"
  ],
  "system_prompt_lines": [
    "regle d'ecriture extraite 1 (formule directement injectable dans un prompt LLM)",
    "regle 2",
    "regle 3",
    "regle 4",
    "regle 5",
    "regle 6"
  ]
}}

Reponds UNIQUEMENT en JSON valide, sans markdown, sans explication."""


NICHE_MAP = {
    "kebane":    "culture, societe, storytelling personnel, humour, vie quotidienne africaine",
    "niche_ia1": "intelligence artificielle, outils IA, productivite, business en ligne",
    "owwstin":   "intelligence artificielle, automatisation, entrepreneuriat digital",
    "yikchan":   "intelligence artificielle, outils IA, creation de contenu, business",
}


def _call_groq(prompt: str) -> str | None:
    if not GROQ_API_KEY:
        print("[ANALYZER] GROQ_API_KEY manquant dans .env")
        return None
    try:
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 3000,
            },
            timeout=60
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        print(f"[ANALYZER] Groq {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[ANALYZER] Groq error: {e}")
    return None


def _parse_json(raw: str) -> dict | None:
    # Chercher le JSON dans la reponse
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def analyze_slug(slug: str, posts: list[dict]) -> dict | None:
    if not posts:
        print(f"  [!] Aucun post pour '{slug}', analyse ignoree.")
        return None

    niche   = NICHE_MAP.get(slug, "contenu Facebook")
    sample  = posts[:25]  # max 25 posts envoyes a Groq
    posts_text = "\n\n---\n\n".join(
        f"[POST {i+1}]\n{p['text'][:600]}"
        for i, p in enumerate(sample)
    )

    print(f"\n[{slug}] Analyse de {len(sample)} posts via Groq...")

    prompt = ANALYSIS_PROMPT.format(
        n=len(sample),
        slug=slug,
        niche=niche,
        posts_sample=posts_text,
        jm_context=JM_CONTEXT,
    )

    import time
    time.sleep(15)  # eviter rate limit Groq (12k TPM)
    raw = _call_groq(prompt)
    if not raw:
        return None

    data = _parse_json(raw)
    if not data:
        print(f"  [!] Parse JSON echoue pour '{slug}'")
        print(f"  Reponse brute : {raw[:300]}")
        return None

    print(f"  -> Analyse OK : persona '{data.get('nom_persona', slug)}'")
    return data


def _write_persona(slug: str, data: dict, posts: list[dict]):
    """Ecrit les fichiers persona dans personas/cerveau_<slug>/"""
    folder = PERSONAS_DIR / f"cerveau_{slug}"
    folder.mkdir(parents=True, exist_ok=True)

    nom          = data.get("nom_persona", slug)
    niche        = data.get("niche", "")
    hooks        = data.get("signature_hooks", [])
    structures   = data.get("structure_posts", [])
    ton          = data.get("ton_vocabulaire", {})
    engagement   = data.get("patterns_engagement", {})
    sujets       = data.get("sujets_angles", [])
    hooks_jm     = data.get("exemples_hooks_adaptes_jm", [])
    prompt_lines = data.get("system_prompt_lines", [])

    # ── system_prompt.md ────────────────────────────────────────────
    sp = f"""# Persona : {nom}
> Source : page Facebook "{slug}" | Niche : {niche}

## Ce que fait ce cerveau
{niche}

## Formules d'accroche (hooks)
{chr(10).join(f'- {h}' for h in hooks)}

## Structures de posts
{chr(10).join(f'- {s}' for s in structures)}

## Ton et vocabulaire
- Registre : {ton.get('registre', '')}
- Expressions signature : {', '.join(ton.get('expressions_signature', []))}
- Ce qu'il evite : {', '.join(ton.get('ce_qu_il_evite', []))}

## Strategie d'engagement
- CTAs utilises : {', '.join(engagement.get('cta_types', []))}
- Types de questions : {', '.join(engagement.get('questions_types', []))}
- Strategie commentaire : {engagement.get('commentaire_strategy', '')}

## Sujets et angles privilegies
{chr(10).join(f'- {s}' for s in sujets)}

## Regles d'ecriture (a injecter dans les prompts LLM)
{chr(10).join(f'{i+1}. {r}' for i, r in enumerate(prompt_lines))}
"""
    (folder / "system_prompt.md").write_text(sp, encoding="utf-8")

    # ── examples.md ─────────────────────────────────────────────────
    ex = f"""# Exemples de hooks adaptes a Jean-Marc ({nom})

Ces hooks sont issus de l'analyse du cerveau "{slug}"
et reformules pour l'univers Jean-Marc (IA, dev, business, culture, Africa).

{chr(10).join(f'## Hook {i+1}{chr(10)}{h}{chr(10)}' for i, h in enumerate(hooks_jm))}

---

## Posts bruts originaux (reference)
> Extraits du scraping — utilisables comme inspiration directe.

{chr(10).join(f'### Post {i+1}{chr(10)}{p["text"][:400]}{chr(10)}' for i, p in enumerate(posts[:10]))}
"""
    (folder / "examples.md").write_text(ex, encoding="utf-8")

    # ── config.json ─────────────────────────────────────────────────
    config = {
        "nom_persona": nom,
        "slug_source": slug,
        "niche_source": niche,
        "usage": "Injecter system_prompt.md dans le prompt Groq pour imiter ce cerveau",
        "ton": ton.get("registre", ""),
        "format_principal": "trigger court + details en commentaire",
        "hooks_signature": hooks,
        "sujets_prioritaires": sujets,
    }
    (folder / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"  Persona ecrit : {folder}")
    print(f"    system_prompt.md, examples.md, config.json")


def main():
    # Charger le fichier consolide
    all_file = SCRAPED_DIR / "_all.json"
    if not all_file.exists():
        print(f"[!] Fichier scrape introuvable : {all_file}")
        print("Lance d'abord : python tools/fb_scraper.py")
        return

    all_data = json.loads(all_file.read_text(encoding="utf-8"))
    total_posts = sum(len(v) for v in all_data.values())
    print(f"Donnees chargees : {total_posts} posts, {len(all_data)} sources")

    results = {}
    already_done = {"kebane", "niche_ia1"}  # deja analyses, on saute
    for slug, posts in all_data.items():
        if slug in already_done:
            print(f"[{slug}] Deja analyse, ignore.")
            # Charger le config existant pour le hybride
            cfg_file = PERSONAS_DIR / f"cerveau_{slug}" / "config.json"
            if cfg_file.exists():
                cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                results[slug] = {
                    "nom_persona": cfg.get("nom_persona", slug),
                    "system_prompt_lines": [],
                    "signature_hooks": cfg.get("hooks_signature", []),
                    "sujets_angles": cfg.get("sujets_prioritaires", []),
                    "exemples_hooks_adaptes_jm": [],
                }
            continue
        analysis = analyze_slug(slug, posts)
        if analysis:
            results[slug] = analysis
            _write_persona(slug, analysis, posts)

    # ── Persona HYBRIDE Jean-Marc ────────────────────────────────────
    if results:
        _write_hybrid_persona(results, all_data)

    print(f"\nTermine. {len(results)} personas generes dans personas/cerveau_*/")


def _write_hybrid_persona(results: dict, all_posts: dict):
    """Fusionne tous les cerveaux en un seul persona hybride 'Jean-Marc'."""
    print("\n[HYBRIDE] Generation du persona fusionne Jean-Marc...")

    # Collecter toutes les regles et hooks
    all_rules  = []
    all_hooks  = []
    all_sujets = []
    all_hooks_jm = []

    for slug, data in results.items():
        all_rules.extend(data.get("system_prompt_lines", []))
        all_hooks.extend(data.get("signature_hooks", []))
        all_sujets.extend(data.get("sujets_angles", []))
        all_hooks_jm.extend(data.get("exemples_hooks_adaptes_jm", []))

    # Demander a Groq de fusionner en un seul persona JM
    fusion_prompt = f"""Tu es un expert en personal branding et copywriting Facebook.

Voici des regles d'ecriture extraites de {len(results)} cerveaux differents :

REGLES EXTRAITES :
{chr(10).join(f'- {r}' for r in all_rules)}

HOOKS SIGNATURE :
{chr(10).join(f'- {h}' for h in all_hooks[:15])}

SUJETS/ANGLES :
{chr(10).join(f'- {s}' for s in all_sujets[:20])}

CONTEXTE Jean-Marc DANSI :
{JM_CONTEXT}

Produis un system prompt complet (500-700 mots) pour un LLM qui va generer des posts Facebook
au nom de Jean-Marc DANSI. Ce prompt doit :
1. Fusionner le meilleur de chaque cerveau
2. Etre specifique au contexte JM (Africa, IA, dev, culture, business)
3. Inclure les formules de hooks les plus efficaces
4. Definir clairement la strategie "trigger court + details en commentaire"
5. Donner 5 exemples de hooks concrets sur des sujets JM

Ecris DIRECTEMENT le system prompt (pas de JSON, pas d'explication, juste le texte du prompt)."""

    raw = _call_groq(fusion_prompt)
    if not raw:
        return

    folder = PERSONAS_DIR / "cerveau_jm_hybride"
    folder.mkdir(parents=True, exist_ok=True)

    hybrid_sp = f"""# Persona Hybride — Jean-Marc DANSI
> Fusionne les cerveaux : {', '.join(results.keys())}
> Genere automatiquement par fb_analyzer.py

{raw}
"""
    (folder / "system_prompt.md").write_text(hybrid_sp, encoding="utf-8")

    # examples.md avec les meilleurs hooks JM
    ex = f"""# Hooks adaptes Jean-Marc — Fusion des {len(results)} cerveaux

{chr(10).join(f'- {h}' for h in all_hooks_jm)}
"""
    (folder / "examples.md").write_text(ex, encoding="utf-8")

    config = {
        "nom_persona": "Jean-Marc DANSI — Hybride",
        "sources": list(results.keys()),
        "usage": "Persona principal a injecter dans script_generator.py pour tous les posts JM",
        "format_principal": "trigger court (1-3 lignes) + details en commentaire",
        "sujets_prioritaires": list(set(all_sujets))[:10],
    }
    (folder / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"  Persona hybride ecrit : {folder}")


if __name__ == "__main__":
    main()
