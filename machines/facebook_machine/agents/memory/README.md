# 🧠 Memory — Mémoire du Système

Ce nœud gère l'historique de tous les posts générés et publiés. Il permet au système d'éviter les répétitions de sujets et de savoir quels posts ont déjà été publiés.

## Interface principale

```python
from agents.memory.agent import (
    get_recent_topics,      # Sujets des 30 derniers jours
    format_recent_for_planner,  # Texte injecté dans le prompt du Topic Finder
    mark_as_published,      # Appeler après chaque publication réussie
    approve_post,           # Approuver un post pending
    list_pending,           # Lister les posts en attente
)
```

## Fonctions

| Fonction | Rôle |
|---|---|
| `get_recent_topics(days=30)` | Liste les sujets générés récemment |
| `get_recent_personas(days=7)` | Compte les personas utilisés cette semaine |
| `format_recent_for_planner(days=30)` | Injecte l'historique dans le prompt du Topic Finder |
| `mark_as_published(folder_path)` | Marque un post comme publié dans meta.json |
| `approve_post(folder_path)` | Change le status de `pending` à `approved` |
| `list_pending()` | Retourne tous les posts `status=pending` |

## Qui l'appelle ?

- **Topic Finder** → `format_recent_for_planner()` pour ne jamais répéter un sujet
- **Publisher** → `mark_as_published()` après chaque succès de publication
- **Dashboard** → `list_pending()` pour afficher la file d'attente

## CLI

```bash
python agent.py --pending              # Lister les posts en attente
python agent.py --approve NOM_DOSSIER  # Approuver un post
python agent.py --approve-all          # Approuver tous les pending
python agent.py --recent 14            # Posts des 14 derniers jours
```

## Données

Toutes les données vivent dans `content/*/meta.json`. Aucune base de données externe.
