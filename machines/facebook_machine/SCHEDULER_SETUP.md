# Configuration du Scheduler Windows

## Option A — Windows Task Scheduler (recommandé)

### Étape 1 : Créer la tâche
1. Ouvrir "Planificateur de tâches" (Task Scheduler)
2. Actions → Créer une tâche de base
3. Nom : `IncidenX Facebook Machine`
4. Déclencheur : Au démarrage
5. Action : Démarrer un programme
6. Programme : `D:\Content_Machine\machines/facebook-machine\start_machine.bat`
7. Terminer

### Étape 2 : Vérifier
- Redémarrer Windows
- Vérifier que le processus Python tourne en arrière-plan
- Consulter `errors.log` pour les logs

## Option B — Script .bat avec démarrage automatique

Le fichier `start_machine.bat` est déjà créé :
```batch
@echo off
cd /d D:\Content_Machine\machines/facebook-machine
python main.py schedule
```

Pour ajouter au démarrage :
1. Copier `start_machine.bat`
2. Coller dans : `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`

## Commandes manuelles

```bash
# Démarrer le scheduler
python main.py schedule

# Générer un post unique
python agents/agent_scheduler.py --once expert_ia

# Voir le contenu généré
python main.py list
```
