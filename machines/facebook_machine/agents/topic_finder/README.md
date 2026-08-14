# Topic Finder Agent

**Rôle** : Générer le plan complet de la journée (les posts et les réels).

## Comment ça marche ?
Ce nœud utilise le LLM `Qwen3` via l'API Groq pour créer un fichier JSON (le "Plan du Jour") dans `content/plans/YYYY-MM-DD_plan.json`. 
Il s'appuie sur le contexte global de la marque (`personas/_shared`) et l'historique de publication (mémoire) pour éviter les répétitions.

## Entrées / Sorties

*   **Variables d'environnement requises :** `GROQ_API_KEY`
*   **Fonction principale :** `generate_daily_plan(date: str = None, force: bool = False) -> AgentResult`
*   **Retour (`AgentResult.data`) :** 
    ```json
    {
      "date": "2026-04-10",
      "posts": [
         { "persona": "kebane_story", "sujet": "..." },
         ...
      ],
      "reels": [
         { "persona": "freelance", "sujet": "..." }
      ]
    }
    ```

## En cas d'échec
Le nœud retournera `success=False` si:
1. `GROQ_API_KEY` est manquant.
2. L'API Groq est injoignable ou en timeout.
3. Le JSON retourné par le modèle est malformé (`JSONDecodeError`).
