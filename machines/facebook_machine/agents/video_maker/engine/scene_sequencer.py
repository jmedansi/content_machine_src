# scene_sequencer.py -- Séquenceur de scènes avec variété visuelle
# Thèmes, animations, et structures variées

from pathlib import Path
import random
import json

# Règles par type de scène (durée + thème visuel)
SCENE_RULES = {
    "hook":         (2.5, 3.5,  "dark"),      # Accroche - sombre et impactant
    "stat":         (3.0, 4.0,  "neon"),     # Stats - couleurs vives
    "tip":          (3.5, 4.5,  None),        # Tips - thème aléatoire
    "proof":        (3.5, 4.5,  "warm"),     # Preuves - tons chaleureux
    "cta":          (3.0, 4.0,  "contrast"),  # CTA - toujours contrastant
    "lottie":       (3.0, 5.0,  "white"),
    "image_text":   (3.5, 5.0,  "image"),
}

# 8 thèmes visuels différents
THEMES = {
    "dark": {
        "bg":       "#020617",
        "text":     "#f8fafc",
        "accent":   "#d4af37",
        "gradient": "linear-gradient(145deg, #020617 0%, #0c1a3a 55%, #020617 100%)",
    },
    "white": {
        "bg":       "#f8fafc",
        "text":     "#0f172a",
        "accent":   "#d4af37",
        "gradient": "linear-gradient(145deg, #f8fafc 0%, #e2e8f0 100%)",
    },
    "contrast": {
        "bg":       "#d4af37",
        "text":     "#020617",
        "accent":   "#020617",
        "gradient": "linear-gradient(145deg, #d4af37 0%, #f5d97a 50%, #d4af37 100%)",
    },
    "image": {
        "bg":       "#020617",
        "text":     "#f8fafc",
        "accent":   "#d4af37",
        "gradient": None,
    },
    "neon": {
        "bg":       "#0f0f1a",
        "text":     "#00ff87",
        "accent":   "#ff006e",
        "gradient": "linear-gradient(145deg, #0f0f1a 0%, #1a0a2e 100%)",
    },
    "warm": {
        "bg":       "#1a1208",
        "text":     "#fef3c7",
        "accent":   "#f59e0b",
        "gradient": "linear-gradient(145deg, #1a1208 0%, #2d1f0f 100%)",
    },
    "ocean": {
        "bg":       "#0c1929",
        "text":     "#7dd3fc",
        "accent":   "#06b6d4",
        "gradient": "linear-gradient(145deg, #0c1929 0%, #164e63 100%)",
    },
    "minimal": {
        "bg":       "#ffffff",
        "text":     "#18181b",
        "accent":   "#3b82f6",
        "gradient": "linear-gradient(145deg, #ffffff 0%, #f4f4f5 100%)",
    },
}

# Animations différentes
ENTRANCE_DIRECTIONS = ["bottom", "left", "right", "top", "zoom_in", "fade"]

# Styles de texte possibles
TEXT_STYLES = [
    "bold_large", "minimal", "centered", "left_aligned", "uppercase"
]

# Structuration PPCA alternative
PPCA_ROLES = {
    0: "hook",
    1: "proof",
    2: "consequence",
    3: "solution",
    4: "ease",
    5: "cta",
}


def validate_contrast(scenes: list) -> list:
    """Vérifie qu'on n'a jamais 2 scènes de même thème en consécutif."""
    result = []
    prev_theme = None
    
    for scene in scenes:
        scene_type = scene.get("type", "unknown")
        _, _, default_theme = SCENE_RULES.get(scene_type, (0, 0, "dark"))
        
        current_theme = scene.get("_theme_name", default_theme)
        
        # Si même thème que le précédent, changer
        if current_theme == prev_theme:
            # Choisir un thème différent
            available = [t for t in THEMES.keys() if t != prev_theme]
            new_theme = random.choice(available)
            scene = {**scene, "_theme": THEMES[new_theme], "_theme_name": new_theme}
        
        result.append(scene)
        prev_theme = scene.get("_theme_name", current_theme)
    
    return result


def assign_themes(scenes: list) -> list:
    """Assigne un thème visuel à chaque scène avec variety."""
    result = []
    theme_cycle = ["dark", "white", "neon", "warm", "ocean", "minimal"]
    
    for i, scene in enumerate(scenes):
        scene_type = scene.get("type", "unknown")
        _, _, default_theme = SCENE_RULES.get(scene_type, (0, 0, "dark"))
        
        # CTA toujours contrast
        if scene_type == "cta":
            theme_name = "contrast"
        # Proof toujours warm
        elif scene_type == "proof":
            theme_name = "warm"
        # Hook toujours dark
        elif scene_type == "hook":
            theme_name = "dark"
        # Stat toujours neon
        elif scene_type == "stat":
            theme_name = "neon"
        else:
            # Tips : cycle à travers les thèmes
            theme_name = theme_cycle[i % len(theme_cycle)]
        
        theme_data = THEMES.get(theme_name, THEMES["dark"])
        scene = {**scene, "_theme": theme_data, "_theme_name": theme_name}
        result.append(scene)
    
    return result


def assign_animations(scenes: list) -> list:
    """Assigne des animations variées à chaque scène."""
    result = []
    
    for i, scene in enumerate(scenes):
        # Direction d'entrée différente pour chaque slide
        entrance = ENTRANCE_DIRECTIONS[i % len(ENTRANCE_DIRECTIONS)]
        
        # Style de texte différent
        text_style = TEXT_STYLES[i % len(TEXT_STYLES)]
        
        scene = {
            **scene,
            "_entrance": entrance,
            "_text_style": text_style,
        }
        result.append(scene)
    
    return result


def randomize_duration(scenes: list) -> list:
    """Ajoute de la variété dans les durées."""
    result = []
    for scene in scenes:
        scene_type = scene.get("type", "unknown")
        min_dur, max_dur, _ = SCENE_RULES.get(scene_type, (3, 4, "dark"))
        
        # Durée aléatoire dans la plage
        duration = random.uniform(min_dur, max_dur)
        scene = {**scene, "duration": round(duration, 1)}
        result.append(scene)
    
    return result


def sequence_scenes(script: list) -> list:
    """Pipeline complet de séquençage avec variété."""
    script = assign_themes(script)
    script = assign_animations(script)
    script = validate_contrast(script)
    script = randomize_duration(script)
    return script


def script_from_segments(segments: list, image_paths: list = None) -> list:
    """Convert segments (textes) en script de slides."""
    script = []
    
    for i, seg in enumerate(segments):
        if i == 0:
            slide_type = "hook"
        elif i == len(segments) - 1:
            slide_type = "cta"
        elif i <= 3:
            slide_type = "tip"
        else:
            slide_type = "proof"
        
        scene = {
            "type": slide_type,
            "title": seg.get("title", ""),
            "subtitle": seg.get("subtitle", ""),
            "text": seg.get("text", ""),
            "narration": seg.get("text", ""),
            "lottie_keyword": seg.get("lottie_keyword", "star"),
            "duration": 3.5 if slide_type == "hook" else 4.0,
        }
        
        if slide_type == "tip":
            scene["number"] = i
        
        script.append(scene)
    
    script = assign_themes(script)
    script = assign_animations(script)
    script = randomize_duration(script)
    
    return script


def load_script_from_file(file_path: str) -> list:
    """Load script from JSON file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return sequence_scenes(data)
    except Exception as e:
        print(f"[SEQUENCER] Load error: {e}")
    return None


if __name__ == "__main__":
    # Test
    test_script = [
        {"type": "hook", "title": "Tu perds 70% de tes clients ?", "subtitle": "Voici pourquoi et comment éviter ça."},
        {"type": "tip", "number": 1, "title": "Sois visible 24h/24", "subtitle": "Un site web = votre meilleure vitrine."},
        {"type": "tip", "number": 2, "title": "Réponds en 5 minutes", "subtitle": "速度 = confiance pour les clients."},
        {"type": "tip", "number": 3, "title": "Demande des témoignages", "subtitle": "Les preuves sociales convertissent."},
        {"type": "proof", "title": "71% des clients choose who responds fastest", "subtitle": "Étude Harvard Business Review 2024"},
        {"type": "cta", "title": "Commente TON astuce", "subtitle": "Je partage les meilleures en MP"},
    ]
    
    result = sequence_scenes(test_script)
    print(json.dumps(result, indent=2, ensure_ascii=False))