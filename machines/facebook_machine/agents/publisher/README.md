# Publisher Agent

**Rôle** : Publier de manière autonome sur la page Facebook. Il gère trois types de publications:
1. Les posts textes simples (Feed)
2. Les posts avec image (Photos URL)
3. Les posts vidéos courts (Reels GraphQL)

Il peut utiliser deux voies distinctes pour poster:
*   Via **Facebook Graph API** directement (recommandé et géré en natif).
*   Via un webhook **Make.com** (fallback déprécié, au cas où l'API Meta bloque le jeton).

## Comment ça marche ?
1. Le nœud lit `facebook_post.txt` dans le dossier fourni.
2. Il vérifie `meta.json` pour savoir si une `image_url` existe ou si un film Reel est présent (`reel.mp4`).
3. Il lance la commande de post sur l'API Graph (`POST /feed`, `POST /photos` ou `POST /video_reels`).
4. Si le post contient un "CTA" configuré dans `resource.json` (ex: "Commentez GUIDE"), l'agent Publisher va sauvegarder ce trigger_word et la réponse dans `data/post_resources.json` pour informer le **Webhook Monitor** des réponses à envoyer en messages privés.
5. Il ajoute `published=True` au `meta.json`.

## Entrées / Sorties

*   **Variables d'environnement requises :** `FB_PAGE_ID`, `FB_PAGE_ACCESS_TOKEN`, `MAKE_WEBHOOK_URL` (optionnel).
*   **Fonction principale :** `run_publisher(folder_path: str, use_graph_api=True) -> AgentResult`
*   **Retour (`AgentResult.data`) :**
    ```json
    {
      "post_id": "123456789_987654321",
      "reel_id": "987654"
    }
    ```

## En cas d'échec
Le nœud retournera `success=False` si:
1. Le token Meta a expiré (erreur classique `OAuthException` qu'il faut traquer dans les logs de ce nœud).
2. Le fichier post n'est pas trouvé.
3. L'API Make retourne une erreur HTTP autre que 200.
