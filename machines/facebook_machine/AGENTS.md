# IncidenX Facebook Machine — Fonctionnement actuel

Système complet de génération et publication automatique de contenu Facebook pour Jean-Marc DANSI — *"Le Taximan du Digital"*. Tout est automatisé : planification, rédaction, images, réels, publication, cross-posting Instagram, auto-DM sur commentaire, posting dans les groupes.

---

## 1. Architecture en bref

```
05h00 (auto)     → topic_finder        génère le plan du jour (via core/llm_router)
                   └─ content/plans/YYYY-MM-DD_plan.json
                      · N posts (autant que de personas actifs)
                      · 1 reel

06h00..21h00     → scheduler           exécute chaque post du plan
   ├─ process_single_post  → copywriter       rédige le post (via core/llm_router)
   │                           image_creator  génère l'image (Groq + Gemini/Pexels)
   │                           publisher       publie sur Facebook (Graph API)
   │                                            cross-post Instagram (si lié)
   ├─ process_reel        → video_maker       génère le reel vidéo depuis reel_brief.txt
   │                           publisher       publie Reels Facebook (3 phases API)
   └─ group_poster         → agent_group_poster poste dans 3 groupes FB via Playwright

En parallèle :
webhook_server --poll  → vérifie toutes les 10 min les commentaires et déclenche auto-DM
                          quand un trigger_word est détecté
```

---

## 2. Planning quotidien (dynamique — basé sur les personas actifs)

Le planning est généré dynamiquement : le topic_finder lit les dossiers dans `personas/` et crée autant de posts que de personas actifs.

**Personas actifs actuellement** (dynamiques — automatiquement détectés) :
- `batisseur`, `cta`, `denicheur`, `forgeron`, `franc_tireur`, `post_court`, `post_trigger`

**Personas ignorés** : `_shared/`, `_archives/`, `all.txt`

Pour ajouter un persona, crée simplement un dossier dans `personas/`. Pour le désactiver, renomme-le avec `_` prefix ou déplace-le dans `_archives/`.

**Total : N posts + 1 reel / jour** (N = nombre de dossiers personas actifs)

---

## 3. Structure du projet

```
facebook-machine/
├── .env                         # Tokens API + config
├── config_manager.py            # Centralise les variables Facebook
├── agents/
│   ├── scheduler/
│   │   └── agent.py             # Orchestre le pipeline batch
│   ├── topic_finder/
│   │   └── agent.py             # Génère le plan du jour (Groq Qwen3-32B)
│   ├── copywriter/
│   │   └── agent.py             # Rédige les posts (Ollama DeepSeek)
│   ├── image_creator/
│   │   └── agent.py             # Génère l'image (Groq + Gemini/Pexels)
│   ├── video_maker/
│   │   └── agent.py             # Génère les reels (FFmpeg + TTS)
│   ├── publisher/
│   │   └── agent.py             # Publie sur Facebook + Instagram
│   └── group_poster/
│       └── agent.py             # Poste dans les groupes (Playwright)
├── personas/                    # Dossiers dynamiques — chaque dossier = 1 persona actif
│   ├── _shared/
│   │   ├── brand_voice.md       # Identité "Le Taximan du Digital"
│   │   ├── objectives.md        # 3 audiences + 3 objectifs
│   │   └── accroches.md         # Patterns d'accroches
│   ├── batisseur/
│   ├── cta/
│   ├── denicheur/
│   ├── forgeron/
│   ├── franc_tireur/
│   └── post_court/
├── core/
│   ├── config.py                # Configuration centralisée
│   ├── task_tracker.py          # Suivi progression SQLite
│   └── groq_router.py           # Routeur multi-clé Groq
├── content/
│   ├── plans/                   # Plans quotidiens générés
│   │   └── YYYY-MM-DD_plan.json
│   └── YYYY-MM-DD_persona/      # Un dossier par post
│       ├── facebook_post.txt
│       ├── image.webp
│       └── meta.json
└── dashboard_api_v2.py          # API FastAPI + Dashboard
```

---

## 4. Personas (dynamiques)

| Persona | Rôle | Mots | Fréquence |
|---------|------|------|-----------|
| `kebane_humain` | Anecdotes personnelles, storytelling | 400-600 | 1×/jour (06h) |
| `kebane_roadmap` | Chemin complet, 5 actes, contraintes africaines | 1500-2500 | 1×/jour (12h) |
| `kebane_verdict` | Verdict tranché sur un sujet concret | 400-700 | 1×/jour (15h30) |
| `historien` | Fait historique africain ou mondial | 500-800 | 1×/jour (18h30) |
| `expert_ia` | Cas concret tech / outil testé | 300-500 | 1×/jour (09h) |
| `cta` | Post + ressource gratuite (trigger word) | 300-500 | 2×/jour (08h, 14h) |
| `post_court` | Micro-vérité / stat / question / teaser | 20-100 | 8×/jour |
| `mini_formation` (compte 2) | Formation complète IA (120 séances) | 200-500 | 2×/jour (09h, 18h) |

### Persona `mini_formation` (Compte 2 — "L'IA de Zéro à 100")

**Format :** `formation` — post long avec cours complet + exercice dans le post lui-même. Pas de teaser.

**Structure post :**
```
🧠 SÉANCE X/120 : [TITRE]
════════════════════
📋 AU PROGRAMME
════════════════════
● Objectif 1 ● Objectif 2 ● Objectif 3

✧ ✧ ✧

════════════════════
📖 LE COURS
════════════════════
[Cours avec ◈ ▸ ●, 3-5 paragraphes, analogies, ton pédagogue]

✧ ✧ ✧

════════════════════
✍️ EXERCICE
════════════════════
[Exercice 5 min + exemple]
Abonne-toi pour ne rien rater des prochaines séances...

#JM
---IMAGE PROMPT---
[prompt technique en anglais]
```

**Pipeline :**
1. `planned_topics.json` (120 sessions prédéfinies)
2. Copywriter → extrait `---IMAGE PROMPT---` (pas de JSON), génère `trigger_comments.json`
3. `humanize_pass` désactivé pour ce format (préserve la structure)
4. `post_process_formation_text()` garantit 🧠📋📖✍️ et ═════/✧ séparateurs
5. Image creator lit `image_prompt` depuis `meta.json`
6. 2 commentaires automatiques (publisher): Commentaire 1 en haut "Je t'offre une formation...", Commentaire 2 en bas "Tu as appris à :..."

**Modèle :** `llama-3.3-70b-versatile` (Groq) — pas de 8B

**Plan de cours :** `plan_cours_par_sujet.md` — 120 séances en 4 modules

**Dossier persona :** `accounts/2/persona/mini_formation/` (config: `format: formation`, `target_words: 300`, `humanize_pass: false`)

Important : le publisher vérifie l'EXISTENCE du fichier `trigger_comments.json` (pas le nom du persona) pour déclencher les commentaires.

Les personas sont dynamiques : chaque dossier dans `personas/` (sauf `_shared/`, `_archives/`, `all.txt`) est un persona actif.

Pour ajouter/supprimer un persona, ajoute ou supprime simplement un dossier dans `personas/`. Le topic_finder et le scheduler détectent automatiquement la liste.

Chaque persona contient :
- `system_prompt.md` — instructions complètes pour l'IA
- `config.json` — paramètres (mots min/max, format, humanize_pass, etc.)
- `examples.md` — exemples à suivre

---

## 5. Pipeline de génération (flow détaillé)

1. **Scheduler** → `run_pipeline("all")`
2. **Topic Finder** charge les personas dynamiques → génère `content/plans/YYYY-MM-DD_plan.json`
3. Pour chaque post du plan :
   - **Copywriter** charge `personas/{persona}/` → génère le post via `core/llm_router` (modèle/clé du compte, sinon modèle par défaut global, fallback Groq en dernier recours)
   - Loop vérification mots (retry si hors tolérance)
   - `humanize_pass` si activé → supprime les tournures IA
   - Ajoute signature `— Le Taximan du Digital`
4. Si `persona == cta` : parse `---POST---` / `---RESSOURCE---` → `resource.json` avec trigger_word
5. **Image Creator** génère l'image : Groq concept → Gemini/Simple diffusion → Pexels fallback
6. **Publisher** publie via Graph API :
   - Endpoint `/photos` si image, `/feed` sinon
   - Cross-post Instagram (si lié)
   - Marque `published: true` dans `meta.json`

---

## 6. Génération d'un réel

1. `job_reel(reel_index)` crée `content/YYYY-MM-DD_reel{N}_{slug}/` avec `reel_brief.txt` :
   ```
   SUJET: ...
   PERSONA: freelance|pme|apprenant
   ```
2. `reel_generator.generate_reel_for_post()` :
   - Lit le brief → Groq génère le script en segments (douleur → solution → CTA)
   - Force le dernier segment en CTA commentaire
   - Pour chaque segment : image (Pexels prioritaire) + TTS Piper ou musique
   - FFmpeg : assemblage Ken Burns + sous-titres ASS → `reel/reel.mp4`
3. `publish_reel_video()` publie via **Reels API 3 phases** :
   - Phase 1 : `POST /{page_id}/video_reels?upload_phase=start`
   - Phase 2 : upload binaire vers `upload_url`
   - Phase 3 : `POST /{page_id}/video_reels?upload_phase=finish&video_state=PUBLISHED`
   - Retry 1 fois après 10s si Phase 3 échoue
4. Cross-post Instagram Reels via `/media?media_type=REELS&upload_type=resumable`

---

## 7. Auto-DM sur commentaire (ressources gratuites)

Deux modes disponibles :

### Mode webhook (temps réel)
`webhook_server.py` exposé via ngrok → Facebook envoie les événements comments en temps réel.

### Mode polling (fallback, recommandé si pas d'URL publique)
```bash
python agents/webhook_server.py --poll
```
- Toutes les 10 minutes :
  - GET `/page_id/published_posts` (20 derniers)
  - Pour chaque post ayant un `trigger_word` dans `data/post_resources.json` :
    - GET `/post_id/comments`
    - Pour chaque commentaire contenant le trigger word :
      - Vérifie qu'il n'est pas dans `sent_log.json`
      - Répond au commentaire avec invitation MP
      - Log dans `sent_log.json`

Quand l'utilisateur envoie un MP avec le trigger → `send_messenger_resource()` envoie la ressource complète.

---

## 8. Posting dans les groupes Facebook

`agent_group_poster.py` utilise **Playwright** avec le profil Chrome existant (cookies FB actifs).

**À configurer une fois :**
- `.env` → `CHROME_USER_DATA_DIR=C:\Users\jmeda\AppData\Local\Google\Chrome\User Data`
- `data/facebook_groups.json` : liste des groupes ciblés
  ```json
  [
    {"name": "Freelances Afrique", "url": "https://www.facebook.com/groups/xxx", "audience": "freelance"}
  ]
  ```

**Logique quotidienne (14h00) :**
1. Charge le meilleur post du jour (1er post long/moyen du plan)
2. Groq génère 3 variantes légères (~5-10% différent chacune)
3. Lance Chrome persistant (non-headless, obligatoire pour éviter détection)
4. Pour chaque groupe : navigue → clique "Créer une publication" → tape avec délais humains → publie
5. Espace chaque post de 30-40 min (random)
6. Si 2 échecs consécutifs → arrête la session (protection ban)

**Règles anti-détection :**
- `headless=False` obligatoire
- `--disable-blink-features=AutomationControlled`
- Frappe humaine (40-90ms/caractère)
- Variantes de texte différentes par groupe
- Max 3 groupes/jour par défaut

---

## 9. Variables `.env`

```bash
# --- Ollama (génération locale) ---
OLLAMA_URL=http://localhost:11434

# --- Groq (plan du jour + concepts image) ---
GROQ_API_KEY=gsk_...

# --- Images ---
HF_TOKEN=hf_...
PEXELS_API_KEY=...
POST_IMAGE_ENABLED=true
POST_IMAGE_STYLE=cartoon

# --- Reels ---
REEL_MODE=music    # music | voice

# --- Facebook ---
FB_APP_ID=...
FB_APP_SECRET=...
FB_PAGE_ID=...
FB_PAGE_ACCESS_TOKEN=...
FB_VERIFY_TOKEN=...

# --- Instagram (auto-récupéré) ---
IG_ACCOUNT_ID=

# --- Groupes Facebook ---
CHROME_USER_DATA_DIR=C:\Users\jmeda\AppData\Local\Google\Chrome\User Data
GROUPS_PER_DAY=3
GROUPS_MIN_DELAY_SECONDS=1800

# --- Commentaires ---
AI_RESPONSES_ENABLED=false
```

---

## 10. Commandes utiles

```bash
cd machines/facebook-machine

# Batch complet — génère tous les posts du jour (un à un avec barre de progression)
python agents/scheduler/agent.py
python agents/scheduler/agent.py --date 2026-04-25     # date spécifique
python agents/scheduler/agent.py --type cta             # un persona spécifique
python agents/scheduler/agent.py --type reel           # reel seulement

# Générer le plan manuellement
python agents/topic_finder/agent.py
python agents/topic_finder/agent.py --force            # force la régénération

# API Dashboard
python dashboard_api_v2.py
# → http://localhost:8000 (Dashboard + API)

# Auto-DM — mode polling
python agents/webhook_server.py --poll

# Posting groupes — test manuel
python agents/agent_group_poster.py --list
python agents/agent_group_poster.py --run

# Générer un réel depuis un brief manuel
python agents/reel_generator.py content/2026-04-06_reel1_xxx
```

---

## 11. Identité de marque

**Jean-Marc DANSI — Le Taximan du Digital**

*"Je conduis mes passagers vers la réussite digitale. Monte. Le trajet commence."*

- 3 audiences : **freelance**, **pme**, **apprenant**
- 3 objectifs : **notoriété (40%)**, **engagement (35%)**, **autorité (25%)**
- Ancré Afrique francophone : FCFA, contraintes locales, réalité terrain
- Ton direct, pas de langue de bois, signé `— Le Taximan du Digital`

Tous les détails dans `personas/_shared/objectives.md` et `brand_voice.md`.
