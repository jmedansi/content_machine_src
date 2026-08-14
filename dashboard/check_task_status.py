import sys
sys.path.append('.')
import requests

try:
    response = requests.get('http://localhost:8000/api/tasks?platform=facebook&account_id=1', timeout=5)
    if response.status_code == 200:
        data = response.json()
        tasks = data.get('tasks', [])
        print(f'Tâches actives: {len(tasks)}')
        for task in tasks:
            print(f'  ID: {task["id"]}, Status: {task["status"]}, Progress: {task["progress"]}%')
            print(f'    Message: {task["message"][:100]}...')
            if task['status'] == 'running' and task['progress'] >= 100:
                print('    ⚠️  Tâche terminée mais toujours en running!')
    else:
        print(f'Erreur: {response.status_code}')
except Exception as e:
    print(f'Erreur: {e}')