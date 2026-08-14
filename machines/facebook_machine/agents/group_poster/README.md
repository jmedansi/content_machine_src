# Group Poster Agent

**Rôle** : Nœud de diffusion externe utilisant Playwright pour publier automatiquement (et de manière humaine) le contenu de la Content Machine dans les groupes Facebook pertinents.

## Comment ça marche ?
1. Le nœud lit `data/facebook_groups.json` pour trouver les URLs cibles.
2. Il récupère le post du jour (généré par le Copywriter) dans `content/`.
3. Il utilise l'API Groq (Llama 3.3) pour générer N variantes subtiles (5 à 10% différentes) du post pour éviter le ban pour "duplicate content" par l'anti-spam Facebook.
4. Il ouvre un navigateur Chrome persistant via Playwright (profil stocké dans `CHROME_USER_DATA_DIR` pour éviter les requêtes de login).
5. Il tape au clavier le texte comme un humain (délais variables), poste, puis attend plusieurs dizaines de minutes (`GROUPS_MIN_DELAY_SECONDS`) avant le groupe suivant.

## Entrées / Sorties

*   **Variables d'environnement requises :** `CHROME_USER_DATA_DIR` (chemin absolu vers le profil Chrome), `GROQ_API_KEY` (pour les variations), `GROUPS_PER_DAY`, `GROUPS_MIN_DELAY_SECONDS`.
*   **Fichier requis :** `data/facebook_groups.json` (Liste JSON avec champs "name" et "url").
*   **Fonction principale :** `run_group_poster() -> AgentResult`
*   **Retour (`AgentResult.data`) :**
    ```json
    {
      "targeted_groups": 3,
      "posted_groups_count": 3
    }
    ```

## En cas d'échec
Le nœud retournera `success=False` si:
1. Playwright crash ou Chrome refuse de s'ouvrir.
2. Au bout de 2 échecs consécutifs à trouver les bons sélecteurs (Facebook a mis à jour son UI HTML), le nœud s'arrête par précaution sécuritaire (anti-spam).
