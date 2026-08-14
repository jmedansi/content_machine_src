# 🧊 Gemini Dashboard Pro (IncidenX Version)

Ce projet est une application web autonome (Standalone) permettant de piloter l'IA **Google Gemini (Imagen 3)** pour la création, la modification et le nettoyage d'images professionnelles.

## 📁 Structure du Projet
*   `app.py` : Le serveur **FastAPI**. Il gère les requêtes du Dashboard et coordonne les scripts Python.
*   `gemini_engine.py` : Le moteur **Playwright**. Il automatise Chrome pour interagir avec Gemini. Supporte l'upload de fichiers locaux (`mode="modify"`).
*   `watermark_tool.py` : Le module **OpenCV**. Supprime le logo étoilé de Gemini via Inpainting (Masque proportionnel 15%).
*   `static/` : Contient l'interface utilisateur (HTML/CSS/JS) en style **Glassmorphism Dark**.
*   `uploads/` : Dossier temporaire pour les images que vous uploadez depuis votre PC.

---

## 🛠️ Installation & Lancement

### 1. Dépendances
Dans un terminal ouvert dans ce dossier :
```powershell
pip install -r requirements.txt
```

### 2. Variables d'environnement
Assurez-vous que votre `GITHUB_TOKEN` est bien configuré dans votre système pour l'upload automatique.

### 3. Démarrage
```powershell
python app.py
```
Accédez ensuite à l'interface sur : **`http://127.0.0.1:8000`**

---

## 🚀 Fonctionnalités du Dashboard

### 1. Génération Pure
*   Saisissez votre prompt.
*   Le script ouvre un nouvel onglet, génère l'image, la nettoie et vous donne le lien GitHub.

### 2. Modification d'Image (Upload) ✅
*   Glissez une image de votre ordinateur.
*   Saisissez une commande de modification (ex: "Remplace le fond par une forêt").
*   Le script **uploade l'image sur Gemini**, traite la demande et vous revient avec le résultat nettoyé.

### 3. Nettoyage Express
*   Uploadez une image déjà sur votre PC qui contient un filigrane.
*   Appuyez sur "Effacer les Filigranes".
*   L'image est instantanément traitée en local dans le dossier `uploads/`.

---

## 💎 Technologie Key-Points
*   **Signal "Stop"** : Le script attend que Gemini ait fini d'écrire pour capturer l'image (0 erreur de timing).
*   **Patience Dynamique** : Jusqu'à 15 tentatives de détection d'image pour les générations lentes.
*   **Inpainting NS** : Utilisation des équations de Navier-Stokes pour un lissage invisible du filigrane.

---
*Projet réalisé pour IncidenX - Automatisation Visuelle Haute Performance.*
