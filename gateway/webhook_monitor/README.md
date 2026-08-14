# Webhook Monitor Agent

**Rôle** : Nœud "Always On" agissant comme un démon (serveur FastAPI). Il écoute les interactions entrantes sur la page Facebook (commentaires, DMs) et fournit une API pour un Dashboard de contrôle.

## Comment ça marche ?
Ce nœud a deux missions principales :
1. **Écouter les webhooks de Meta** (`/webhook`) : Dès qu'un utilisateur commente avec le "Trigger Word" (déclaré par le Publisher lors de la publication), l'agent réagit. Il peut aussi générer une réponse conversationnelle pertinente (si `AI_RESPONSES_ENABLED=true`) via Ollama. Ensuite, si l'utilisateur envoie ce mot clé en DM, il lui délivre la ressource associée (Lead Magnet, guide, lien).
2. **Fournir l'API du Dashboard** (`/api/*`) : Permet de monitorer le statut du système (modèles Ollama démarrés, tunnel Cloudflare actif, nombre de posts, etc.).

*Il intègre également un mode "Polling" de secours au cas où les Webhooks Meta seraient bloqués.*

## Entrées / Sorties

*   **Variables d'environnement requises :** L'adresse locale Ollama `OLLAMA_URL`, et les clés Facebook Graph API.
*   **Démarrage :** Ce n'est pas un script ponctuel, il doit être lancé via uvicorn (ex: `start_webhook.bat` qui lance `agents.webhook_monitor.agent:app`).

## En cas d'échec
Cette architecture gère ses propres logs dans `errors.log` et maintient son état en temps réel afin d'être toujours à l'écoute des requêtes HTTP. S'il crash (port 8000 occupé ou API Meta tombé), il faut relancer le batch.
