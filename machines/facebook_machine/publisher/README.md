# publisher — Module autonome de publication CTA sur GitHub Pages

Ce module permet de déployer des pages web sur GitHub Pages sans dépendance externe.

---

## Installation

Copiez le dossier `publisher/` entier dans votre projet.

---

## Configuration (.env)

```bash
# GitHub
GITHUB_TOKEN=votre_token_github
GITHUB_REPO=jmedansi/incidenx-audit
AUDIT_DOMAIN=audit.incidenx.com
GITHUB_BRANCH=main
```

---

## Utilisation

```python
from publisher import publish_cta

# Publish simple
result = publish_cta(
    slug="guide-facebook",
    title="Guide Monetisation Facebook",
    content="# Introduction\n\nVotre contenu..."
)

# Avec theme
result = publish_cta(
    slug="guide-facebook",
    title="Guide Monetisation",
    content="# Introduction\n\n...",
    theme="blue"
)

if result["success"]:
    print(f"URL: {result['url']}")
```

---

## API

### `publish_cta(slug, title, content, theme="default")`

**Paramètres:**
- `slug` (str): Identifiant unique
- `title` (str): Titre de la page
- `content` (str): Contenu Markdown/HTML
- `theme` (str): Thème optionnel — `default`, `blue`, `red`, `purple`

**Retourne:**
- `{"success": True, "url": "https://...", "slug": "..."}`
- `{"success": False, "error": "..."}`

---

## Themes disponibles

| Theme | Couleur primaire | Background |
|-------|---------------|-----------|
| default | #10b981 (green) | #0d1117 |
| blue | #3b82f6 | #1e3a5f |
| red | #ef4444 | #3b1e1e |
| purple | #8b5cf6 | #2e1a3b |

---

## URL publique

`https://{AUDIT_DOMAIN}/{slug}/`

Exemple: `https://audit.incidenx.com/guide-facebook-monetisation-2025/`