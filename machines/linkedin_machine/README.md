# IncidenX — LinkedIn Content Machine

Système automatique de génération et de publication de contenu LinkedIn pour l'agence IncidenX. Utilise Groq (Llama 3.3) pour la rédaction et l'API LinkedIn v2 pour la publication.

## Architecture

- `main.py` : Orchestrateur principal.
- `agents/` : Contient les agents spécialisés (sujets, rédaction, publication, mémoire).
- `data/` : Fichiers JSON pour la persistance locale (secteurs, mémoire, sujets en attente).
- `content/` : Dossiers horodatés contenant les posts rédigés et leurs métadonnées.

## Installation

1. Clonez le dépôt.
2. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. Créez un fichier `.env` basé sur `.env.example` et remplissez vos clés API.
4. Placez votre fichier `service_account.json` pour Google Sheets à la racine.

## Utilisation

### 1. Générer les sujets de la semaine
Génère 10 idées de posts basées sur les secteurs et problèmes définis.
```bash
python main.py
```
Les sujets sont sauvegardés dans `data/topics_pending.json`.

### 2. Valider les sujets
Ouvrez `data/topics_pending.json` et changez `"validated": false` en `"validated": true` pour les sujets que vous souhaitez publier.

### 3. Rédiger les posts
Rédige les posts pour les sujets validés sans les publier.
```bash
python main.py write
```
Les textes se trouvent dans le dossier `content/`.

### 4. Publier
Publie les posts déjà rédigés qui n'ont pas encore été postés.
```bash
python main.py publish
```

## Règles Globales Appliquées
- Python 3.11.
- Commentaires en français.
- Clés API centralisées dans `config_manager.py`.
- Journalisation des erreurs dans `errors.log`.
- Synchronisation systématique avec Google Sheets via `gspread`.
