import os
import glob
from pathlib import Path

target_dir = r"d:\Content_Machine\machines\linkedin_machine\accounts"

json_instructions = """
## FORMAT DE SORTIE (JSON OBLIGATOIRE)
Tu dois renvoyer ta réponse EXCLUSIVEMENT sous forme d'un objet JSON valide contenant exactement ces deux clés :
- `"post_content"` : Le texte complet du post LinkedIn (incluant l'accroche, le développement, etc.).
- `"image_prompt"` : Le prompt technique descriptif en anglais pour générer l'image, basé STRICTEMENT sur les "DIRECTIVES DE GÉNÉRATION D'IMAGE" ci-dessus.

N'ajoute AUCUN texte avant ou après le JSON. N'ajoute pas de balises markdown ```json si possible.
"""

count = 0
for filepath in glob.glob(os.path.join(target_dir, "**", "system_prompt.md"), recursive=True):
    path = Path(filepath)
    content = path.read_text(encoding="utf-8")
    
    if "FORMAT DE SORTIE (JSON OBLIGATOIRE)" not in content:
        content += "\n" + json_instructions
        path.write_text(content, encoding="utf-8")
        print(f"Updated: {filepath}")
        count += 1
    else:
        print(f"Already updated: {filepath}")

print(f"\nTotal files updated: {count}")
