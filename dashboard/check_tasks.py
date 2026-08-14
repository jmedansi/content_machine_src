import sys
sys.path.append('.')
import requests
import json

try:
    response = requests.get('http://localhost:8000/api/tasks?platform=facebook&account_id=1', timeout=5)
    print(f'Status: {response.status_code}')
    print(f'Content-Type: {response.headers.get("content-type", "unknown")}')

    if response.status_code == 200:
        try:
            data = response.json()
            print(f'Type de data: {type(data)}')
            if isinstance(data, dict) and 'tasks' in data:
                tasks = data['tasks']
                print(f'Tâches récupérées: {len(tasks)}')
                for task in tasks:
                    print(f'  {task.get("id", "?")}: {task.get("status", "?")} - {task.get("description", "?")[:50]}...')
            else:
                print(f'Data inattendue: {data}')
        except Exception as json_e:
            print(f'Erreur JSON: {json_e}')
            print(f'Raw text: {response.text[:500]}')
    else:
        print(f'Erreur API: {response.status_code}')
except Exception as e:
    print(f'Erreur: {e}')