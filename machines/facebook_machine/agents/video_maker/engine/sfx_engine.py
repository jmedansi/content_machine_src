# sfx_engine.py -- Mixage SFX sur une piste audio de slide
# Assigne les bons effets sonores selon le type de slide,
# puis les mixe avec la voix TTS via ffmpeg.
#
# SFX par événement :
#   hook  → boom + whoosh_in (entrée percutante)
#   tip   → whoosh_in + pop  (entrée + highlight)
#   proof → success + ding   (fanfare + highlight)
#   cta   → notification + whoosh_in
#
# Usage dans scene_director.py :
#   from sfx_engine import mix_sfx_with_tts
#   mixed = mix_sfx_with_tts(tts_path, slide_type, output_path)

import random
import subprocess
import logging
from pathlib import Path

SFX_DIR  = Path(__file__).parent.parent / "assets" / "sfx"
FFMPEG_PATH = r"C:\ffmpeg\ffmpeg-8.1-essentials_build\bin\ffmpeg.exe"


def _get_ffmpeg() -> str:
    try:
        r = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True, shell=True)
        if r.returncode == 0:
            return r.stdout.strip().split("\n")[0].strip()
    except Exception:
        pass
    if Path(FFMPEG_PATH).exists():
        return FFMPEG_PATH
    return "ffmpeg"


# ---------------------------------------------------------------------------
# Pool de combinaisons SFX par type de slide.
# Chaque entrée est une liste de (sfx_file, delay_sec, volume).
# build_sfx_track() tire une combinaison au hasard + jitter sur délai/volume.
# ---------------------------------------------------------------------------
SFX_POOL = {
    "hook": [
        [("boom.wav", 0.00, 0.55), ("whoosh_in.wav", 0.05, 0.70)],
        [("impact.wav", 0.00, 0.60), ("swoosh.wav", 0.08, 0.65)],
        [("boom.wav", 0.00, 0.50), ("transition.wav", 0.12, 0.55)],
    ],
    "tip": [
        [("whoosh_in.wav", 0.00, 0.60), ("pop.wav", 0.35, 0.80)],
        [("swoosh.wav", 0.00, 0.55), ("ding.wav", 0.30, 0.75)],
        [("transition.wav", 0.00, 0.50), ("pop.wav", 0.40, 0.70)],
        [("whoosh_in.wav", 0.00, 0.65), ("ding.wav", 0.45, 0.65)],
    ],
    "proof": [
        [("whoosh_in.wav", 0.00, 0.50), ("success.wav", 0.25, 0.65), ("ding.wav", 0.55, 0.70)],
        [("swoosh.wav", 0.00, 0.45), ("success.wav", 0.20, 0.70), ("pop.wav", 0.50, 0.75)],
        [("transition.wav", 0.00, 0.50), ("success.wav", 0.30, 0.60)],
    ],
    "cta": [
        [("boom.wav", 0.00, 0.45), ("notification.wav", 0.20, 0.75), ("whoosh_in.wav", 0.10, 0.50)],
        [("impact.wav", 0.00, 0.50), ("notification.wav", 0.25, 0.70)],
        [("boom.wav", 0.00, 0.55), ("swoosh.wav", 0.15, 0.60), ("ding.wav", 0.40, 0.65)],
    ],
    "default": [
        [("transition.wav", 0.00, 0.55)],
        [("whoosh_in.wav", 0.00, 0.50)],
        [("swoosh.wav", 0.00, 0.50)],
    ],
}


def _pick_sfx_combo(slide_type: str) -> list:
    """Tire aléatoirement une combinaison SFX + applique un jitter sur délai/volume."""
    pool = SFX_POOL.get(slide_type, SFX_POOL["default"])
    combo = random.choice(pool)
    # Jitter : ±0.05s sur délai, ±0.08 sur volume
    result = []
    for sfx, delay, vol in combo:
        d = round(max(0.0, delay + random.uniform(-0.05, 0.05)), 3)
        v = round(max(0.2, min(1.0, vol + random.uniform(-0.08, 0.08))), 2)
        result.append((sfx, d, v))
    return result


def _sfx_path(name: str) -> Path | None:
    """Retourne le chemin du SFX, None si absent."""
    p = SFX_DIR / name
    return p if p.exists() else None


def build_sfx_track(slide_type: str, duration: float, output_path: str) -> bool:
    """
    Crée une piste audio WAV contenant les SFX superposés pour ce type de slide.
    Les SFX sont positionnés avec un délai via ffmpeg adelay.
    """
    plan = _pick_sfx_combo(slide_type)
    ffmpeg = _get_ffmpeg()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Filtrer les SFX disponibles
    available = [(sfx, delay, vol) for sfx, delay, vol in plan
                 if _sfx_path(sfx) is not None]

    if not available:
        logging.warning(f"[SFX] Aucun SFX disponible pour '{slide_type}'")
        return False

    # Construire la commande ffmpeg
    cmd = [ffmpeg, "-y"]
    for sfx, _, _ in available:
        cmd += ["-i", str(_sfx_path(sfx))]

    filter_parts = []
    mix_inputs = []

    for i, (sfx, delay_sec, vol) in enumerate(available):
        delay_ms = int(delay_sec * 1000)
        label = f"sfx{i}"
        filter_parts.append(
            f"[{i}:a]adelay={delay_ms}|{delay_ms},volume={vol}[{label}]"
        )
        mix_inputs.append(f"[{label}]")

    n = len(available)
    filter_parts.append(
        f"{''.join(mix_inputs)}amix=inputs={n}:duration=longest:dropout_transition=0[out]"
    )

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[out]",
        "-t", str(duration),
        "-c:a", "pcm_s16le",
        str(out)
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0 and out.exists():
        logging.info(f"[SFX] Track OK: {out.name} ({out.stat().st_size // 1024}KB)")
        return True
    else:
        logging.warning(f"[SFX] Erreur build_sfx_track: {r.stderr[-200:]}")
        return False


def mix_sfx_with_tts(tts_path: str, slide_type: str, duration: float,
                     output_path: str,
                     tts_volume: float = 1.0,
                     sfx_volume: float = 0.7) -> str:
    """
    Mixe la voix TTS avec les SFX du slide.
    Retourne le chemin du fichier mixé (ou tts_path si échec).
    """
    if not tts_path or not Path(tts_path).exists():
        return tts_path

    out = Path(output_path)
    sfx_track = out.parent / f"_sfx_{out.stem}.wav"

    # Générer la piste SFX
    ok = build_sfx_track(slide_type, duration, str(sfx_track))
    if not ok or not sfx_track.exists():
        return tts_path  # fallback : TTS seul

    ffmpeg = _get_ffmpeg()

    # Mixer TTS + SFX
    cmd = [
        ffmpeg, "-y",
        "-i", tts_path,
        "-i", str(sfx_track),
        "-filter_complex",
        f"[0:a]volume={tts_volume}[tts];"
        f"[1:a]volume={sfx_volume}[sfx];"
        "[tts][sfx]amix=inputs=2:duration=longest:dropout_transition=0[aout]",
        "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k",
        str(out)
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    sfx_track.unlink(missing_ok=True)

    if r.returncode == 0 and out.exists():
        logging.info(f"[SFX] Mix OK: {out.name}")
        return str(out)
    else:
        logging.warning(f"[SFX] Mix échoué, fallback TTS: {r.stderr[-200:]}")
        return tts_path


def ensure_sfx_generated():
    """Génère les SFX manquants si nécessaire."""
    missing = [name for name in [
        "whoosh_in.wav", "whoosh_out.wav", "pop.wav", "ding.wav",
        "impact.wav", "swoosh.wav", "notification.wav", "success.wav",
        "transition.wav", "boom.wav"
    ] if not (SFX_DIR / name).exists()]

    if missing:
        print(f"[SFX] Génération de {len(missing)} SFX manquants...")
        from sfx_generator import generate_all
        generate_all()
