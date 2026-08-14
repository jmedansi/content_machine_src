# 📊 Analytics — Rapport des publications

Ce nœud analyse les données de tous les posts générés et produit des statistiques de performance de la machine.

## Interface

```python
from agents.analytics.agent import analyze_content, print_report

stats = analyze_content()
# → {"total": 42, "published": 35, "by_persona": {...}, "avg_word_count": 520, ...}

print_report()  # Affiche le rapport dans le terminal
```

## Données analysées

| Métrique | Description |
|---|---|
| `total` | Nombre total de posts générés |
| `published` | Posts effectivement publiés sur Facebook |
| `unpublished` | Posts en attente ou rejetés |
| `by_persona` | Répartition par persona (kebane_story, cta, etc.) |
| `by_type` | Répartition par type |
| `avg_word_count` | Moyenne du nombre de mots par post |
| `with_images` | Posts ayant une image générée |
| `with_resources` | Posts ayant une ressource CTA attachée |

## Source de données

Toutes les données proviennent des fichiers `content/*/meta.json`. Aucune base de données externe.

## CLI

```bash
python agent.py
# Affiche le rapport complet dans le terminal
```
