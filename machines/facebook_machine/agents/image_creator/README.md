# 🎨 Image Creator — Agent de Génération Visuelle

Ce nœud est **auto-contenu** : tous ses scripts, outils et ressources sont dans ce dossier.
Il peut être déplacé, cloné ou archivé sans rompre aucune dépendance externe.

## Contenu du dossier

```
image_creator/
├── agent.py                  ← Interface principale (run_image_creator)
├── gemini_automation.py      ← Pilotage Playwright pour génération ex-nihilo
├── gemini_engine.py          ← Pilotage Playwright pour modification de photo
├── watermark_tool.py         ← Nettoyage du filigrane Gemini (via inpainting)
├── watermark_eraser_tool.py  ← Nettoyage rapide du filigrane (fallback)
├── JM.png                    ← Photo de profil (utilisée pour posts kebane/CTA)
├── image_prompt.txt          ← Fichier de prompt temporaire (utilisé par l'automation)
├── temp/                     ← Captures et fichiers temporaires
├── uploads/                  ← Images intermédiaires (gemini_engine)
└── README.md                 ← Ce fichier
```

## Comment ça fonctionne

### 1. Décision du mode (`_get_image_mode`)
| Persona | Mode |
|---|---|
| `cta`, `kebane_story`, `kebane_verdict` | ✅ **Photo de l'utilisateur** (JM.png modifiée par IA) |
| Tous les autres | 🖼️ **Image 100% générée** (ex-nihilo par Gemini) |

### 2. Création du concept (`_generate_image_concept`)
L'IA (Groq / Llama 3.3 70b) lit le post complet et agit comme un **Directeur Artistique**.
Elle décrit une scène hyper-réaliste en anglais (personnes d'origine africaine, contexte professionnel).
Si la clé Groq est absente, un concept de fallback générique est utilisé.

### 3. Production de l'image
- **Mode photo** → `gemini_engine.py` : injection par clipboard + modification via Gemini AI
- **Mode génération** → `gemini_automation.py` : prompt texte → Gemini Imagen 3

Les deux scripts pilotent Chrome en **mode debug distant** (port 9222).

### 4. Nettoyage & Sauvegarde
- Suppression du filigrane via `watermark_tool.py`
- Upload sur GitHub (repo public) → URL publique retournée
- Téléchargement local → `post_image.jpg` dans le dossier du post
- Mise à jour de `meta.json` avec `image_url` et `image_failed`

## Interface

```python
from agents.image_creator.agent import run_image_creator

result = run_image_creator("/chemin/vers/dossier/post")
if result.success:
    print(result.data["image_url"])
else:
    print(result.error)
```

## Prérequis
- Chrome ouvert en mode debug : `chrome.exe --remote-debugging-port=9222`
- Variable `.env` : `GROQ_API_KEY`, `GITHUB_TOKEN`
- `playwright`, `groq`, `requests` installés
