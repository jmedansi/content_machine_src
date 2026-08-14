# Copywriter Agent

**Rôle** : Rédiger le texte brut du post Facebook (et son commentaire épinglé si besoin), en respectant la voix de marque, l'audience, les longueurs, et l'objectif fixé par le plan.

## Comment ça marche ?
Ce nœud prend en entrée une instruction de poste (provenant du *Topic Finder* via le *Scheduler*) et utilise un routage local vers Ollama avec le modèle cloud `gemini-3-flash-preview:cloud` pour générer le texte (avec un repli de sécurité sur Groq `Qwen3` si Ollama échoue).

Contrairement à l'ancienne architecture, **cet agent ne gère NI l'image NI le reel**. Sa seule et unique responsabilité est textuelle.

## Entrées / Sorties

*   **Variables d'environnement requises :** `OLLAMA_URL` (par défaut `http://localhost:11434`), `GROQ_API_KEY` (fallback).
*   **Fonction principale :** `run_copywriter(folder_path: str, plan_entry: dict) -> AgentResult`
*   **Traitement :**
    1. Crée le `folder_path` (ex: `content/2026-04-10_sujet_du_post`).
    2. Interroge le LLM.
    3. Vérifie que la consigne de longueur (mots) est respectée et relance le LLM si besoin.
    4. Sauvegarde `facebook_post.txt` et met à jour `meta.json`.
    5. *(Optionnel)* Sauvegarde `pinned_comment.txt` ou `resource.json` si le persona le demande.
*   **Retour (`AgentResult.data`) :** Réplique du `meta.json` mis à jour.

## En cas d'échec
Le nœud retournera `success=False` si:
1. Les API de text-generation sont inaccessibles (Gemini et Groq).
2. Le Persona demandé dans le `plan_entry` n'existe pas dans le dossier `personas/`.
