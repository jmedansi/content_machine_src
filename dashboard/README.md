# IncidenX Content Machine Dashboard

## Démarrage Rapide

### Méthode 1: Script Python Moderne (Recommandé)
```bash
cd Content_Machine/dashboard
python start_dashboard.py
```

Options disponibles:
- `--port 3000` : Port personnalisé
- `--host 0.0.0.0` : Écoute sur toutes les interfaces
- `--background` : Démarrage en arrière-plan
- `--reload` : Rechargement automatique (développement)

### Méthode 2: Script Batch
```bash
cd Content_Machine/dashboard
start_dashboard.bat
```

### Méthode 3: Démarrage Direct
```bash
cd Content_Machine/dashboard
python dashboard_api_v2.py --port 8000
```

### Méthode 4: Script VBS (Silencieux)
Double-cliquez sur `start_dashboard.vbs`

## Démarrage Automatique au Login Windows

Pour démarrer automatiquement le dashboard à chaque connexion Windows:

```powershell
cd Content_Machine/dashboard
.\create_startup_shortcut.ps1
```

Cela crée un raccourci dans le dossier de démarrage de Windows.

## Vérification du Démarrage

Une fois démarré, le dashboard sera accessible sur:
- **Interface Web**: http://localhost:8000
- **Documentation API**: http://localhost:8000/docs
- **Statut API**: http://localhost:8000/api/status

## Fonctionnalités

- ✅ Génération de contenu multi-plateforme (Facebook, LinkedIn, Twitter)
- ✅ Validation et approbation des posts
- ✅ Publication automatique
- ✅ Gestion des comptes et plateformes
- ✅ Interface moderne avec templates HTML
- ✅ API REST complète

## Dépannage

### Port Déjà Utilisé
Si le port 8000 est déjà utilisé:
```bash
python start_dashboard.py --port 3000
```

### Arrêter le Serveur
```bash
# Sur Windows
taskkill /F /IM python.exe

# Ou trouver le processus sur le port 8000
netstat -ano | findstr :8000
taskkill /F /PID <PID>
```

### Logs
Les logs sont disponibles dans:
- `dashboard/out.log` : Sortie standard
- `dashboard/errors.log` : Erreurs

## Architecture

Le dashboard utilise:
- **FastAPI** : Framework web asynchrone
- **Jinja2** : Templates HTML
- **SQLite** : Base de données locale
- **Uvicorn** : Serveur ASGI de production