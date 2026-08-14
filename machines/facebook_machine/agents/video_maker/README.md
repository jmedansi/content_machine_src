# 🎬 Video Maker — Agent de Génération Vidéo

Ce nœud est **auto-contenu** : il peut être déplacé, cloné ou archivé sans rompre aucune dépendance externe.

## Contenu du dossier

```
video_maker/
├── agent.py          ← Interface principale (run_video_maker)
├── README.md         ← Ce fichier
└── engine/           ← Cinema Machine complète (moteur actif)
    ├── scene_director.py      ★ POINT D'ENTRÉE du moteur
    ├── script_generator.py    ← Génère le script AV depuis un topic
    ├── scene_sequencer.py     ← Assigne thèmes et transitions
    ├── slide_renderer.py      ← Rendu HTML → MP4 par slide (Playwright)
    ├── gsap_renderer.py       ← Animations GSAP (stat cards, CTA, hooks)
    ├── chart_renderer.py      ← Graphiques animés (barres, lignes, stats)
    ├── cinema_compositor.py   ← Assemblage final FFmpeg + mixage audio
    ├── tts_engine.py          ← Synthèse vocale (edge-tts)
    ├── subtitle_engine.py     ← Sous-titres ASS brûlés
    ├── sfx_engine.py          ← Bruitage + mixage TTS/SFX
    ├── sfx_generator.py       ← Génération des fichiers SFX
    ├── lottie_library.py      ← Catalogue d'animations Lottie
    ├── lottie_downloader.py   ← Téléchargement JSON Lottie
    └── lottie_bulk_downloader.py ← Téléchargement batch
```

## ⚠️ Moteur actif vs moteur archivé

| Moteur | État | Emplacement |
|---|---|---|
| **Cinema Machine** (Python + Playwright + FFmpeg) | ✅ **ACTIF** | `engine/` |
| Remotion (Node.js / React) | 🗃️ Archivé | `.archive/remotion-engine/` |

Le moteur Remotion a été remplacé par Cinema Machine qui offre plus de contrôle sur les styles visuels (GSAP, Lottie, graphiques) et la synchronisation TTS.

## Pipeline de génération

```
topic (texte)
    │
    ▼
script_generator.py     → Script structuré (6-10 scènes JSON)
    │
    ▼
scene_sequencer.py      → Enrichit chaque scène (thème, entrée, transitions)
    │
    ▼
tts_engine.py           → Génère l'audio TTS par scène (edge-tts)
    │
    ▼
slide_renderer.py       → Rendu Playwright HTML→PNG→MP4 par scène
    │
    ▼
cinema_compositor.py    → Concat FFmpeg + musique de fond + mixage
    │
    ▼
reel.mp4                → Fichier final 1080×1920 30fps
```

## Interface

```python
from agents.video_maker.agent import run_video_maker

result = run_video_maker("/chemin/vers/dossier/post")
if result.success:
    print(result.data["reel_path"])
else:
    print(result.error)
```

## Brief alternatif (sans post Facebook)

Créer un fichier `reel_brief.txt` dans le dossier du post :
```
SUJET: Comment tripler ses tarifs en 30 jours
PERSONA: freelance
```

## Prérequis
- FFmpeg installé et dans le PATH
- `edge-tts` installé : `pip install edge-tts`
- `playwright` installé et navigateur configuré
- `nodejs` (pour Remotion si réactivé)
- Dossier `assets/music/` avec au moins un fichier MP3
