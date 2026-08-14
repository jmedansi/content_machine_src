# Common Core — Services Partagés

Ce dossier contient les **services communs** utilisés par toutes les plateformes (Facebook, LinkedIn, Twitter).

## Structure

```
common/
├── services/
│   ├── api_client.py       # Client HTTP avec rotation des clés Groq
│   └── text_generator.py  # Moteur de génération de texte
│
└── utils/
    └── persona_loader.py # Chargeur универсальный de personas
```

## Utilisation

### Dans une plateforme (ex: LinkedIn)

```python
import sys
sys.path.insert(0, "D:/Content_Machine")

from common.services.text_generator import TextGenerator
from common.utils.persona_loader import load_personas

# Charger les personas LinkedIn
personas = load_personas("linkedin")

# Générer du texte
generator = TextGenerator(platform="linkedin")
result = generator.generate(
    prompt="Écris un post sur...",
    persona="b2b_expert",
    model="llama-3.3-70b-versatile"
)

if result["success"]:
    print(result["text"])
```

### API Client direct

```python
from common.services.api_client import api_client

result = api_client.call_groq(
    prompt="Bonjour",
    system="Tu es un assistant poli.",
    model="llama-3.3-70b-versatile"
)
print(result)
```

## Fonctions utilitaires

### generate_text()
Génération simple en une ligne:

```python
from common.services.text_generator import generate_text

text = generate_text(
    prompt="Titre: 5 conseils pour...",
    platform="linkedin",
    persona="pme_expert"
)
```

### get_available_personas()
Liste les personas:

```python
from common.services.text_generator import get_available_personas

personas = get_available_personas("facebook")
for p in personas:
    print(f"- {p['name']}: {p.get('display_name')}")
```

## Configuration

Les variables d'environnement sont自動iquement chargées depuis `.env`:
- `GROQ_API_KEY`
- `GROQ_API_KEY_2`... `GROQ_API_KEY_9`

---

## Prochaines étapes

1. **Phase 2**: Créer les Adapters pour chaque plateforme
2. **Phase 3**: Implémenter le multi-comptes
3. **Phase 4**: Scheduler intelligent