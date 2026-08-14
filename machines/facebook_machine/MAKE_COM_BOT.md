# Make.com Bot Commentaires — Configuration

## Scénario A — Trigger Word → DM Ressource

### Déclencheur
- **Module** : Facebook Pages - Watch Comments
- **Page ID** : [Votre page Facebook]
- **Filtre** : Contient le trigger word (depuis `resource.json`)

### Action 1 — Répondre au commentaire
- **Module** : Facebook Pages - Create a Comment Reply
- **Message** : "Je t'envoie ça en DM ! 🎁"

### Action 2 — Envoyer la ressource en DM
- **Module** : Facebook Messenger - Send a Message
- **Recipient** : ID de l'utilisateur ayant commenté
- **Message** : Contenu de `resource.json` (à récupérer depuis le webhook)

### Action 3 — Logger (optionnel)
- **Module** : Google Sheets - Add a Row
- **Columns** : user_id, post_id, date, trigger_word

---

## Scénario B — Réponse automatique aux commentaires

### Option 1 — Sans serveur (recommandé)
Réponse générique热情uale définie dans Make.com :
- "Merci pour ton commentaire ! Je reviens vers toi soon."
- "Belle question ! Je prépare une réponse détaillée."

### Option 2 — Avec webhook local (si PC accessible)

#### A. Exposer le PC avec ngrok
```bash
ngrok http 5000
```

#### B. Créer le webhook local
Le fichier `webhook_receiver.py` reçoit les commentaires et génère des réponses via Ollama.

#### C. Configurer Make.com
- **Module** : HTTP - Make a web request
- **URL** : https://votre-ngrok.ngrok.io/webhook
- **Method** : POST
- **Body** : {"text": "{{comment_text}}", "user_id": "{{user_id}}"}

---

## Structure des données

### resource.json (généré par agent)
```json
{
  "type": "cta",
  "content": "Contenu de la ressource...",
  "trigger_word": "IA"
}
```

### meta.json
```json
{
  "topic": "...",
  "persona": "expert_ia",
  "trigger_word": "IA",
  "published": true,
  "published_at": "2026-03-27T..."
}
```

---

## Variables d'environnement pour Make.com

Dans le .env :
```
MAKE_WEBHOOK_URL=https://hook.make.com/xxxxx
OLLAMA_URL=http://localhost:11434
```
