# subtitle_engine.py -- Génère et incruste des sous-titres sur la vidéo finale
# Utilise ffmpeg drawtext pour les brûler dans la vidéo (format Reel standard)
# Les sous-titres sont synchronisés sur les narrations TTS de chaque slide.
#
# Usage :
#   from subtitle_engine import burn_subtitles
#   ok = burn_subtitles(input_mp4, script_with_tts, output_mp4)

import subprocess
import logging
from pathlib import Path

FFMPEG_PATH = r"C:\ffmpeg\ffmpeg-8.1-essentials_build\bin\ffmpeg.exe"
FONTS_DIR   = Path(__file__).parent.parent / "assets" / "fonts"

# Style sous-titres : blanc + ombre noire, centré bas
SUBTITLE_FONT_SIZE  = 52
SUBTITLE_Y_POSITION = "(h-text_h-120)"   # 120px du bas
SUBTITLE_COLOR      = "white"
SUBTITLE_SHADOW     = "black@0.8"
SUBTITLE_FONT       = "Poppins"


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


def _get_font_path() -> str:
    """Retourne le chemin absolu de Poppins-SemiBold."""
    p = FONTS_DIR / "Poppins-SemiBold.ttf"
    if p.exists():
        return str(p).replace("\\", "/").replace(":", "\\:")
    return ""


def _build_ass(script_with_tts: list) -> str:
    """
    Génère un fichier ASS (Advanced SubStation Alpha) depuis le script avec timings TTS.
    Format compatible avec libass et ffmpeg sans besoin de force_style.
    """
    from cinema_compositor import get_video_duration

    # En-tête ASS avec styles
    # PlayResX/Y OBLIGATOIRE : sans ça libass utilise 384x288 comme référence
    # et scale la police de façon aberrante sur une vidéo 1080x1920.
    header = """[Script Info]
Title: Cinema Machine Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Poppins,52,&H00FFFFFF,&H000000FF,&H80000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]
    t_acc = 0.0  # temps accumulé en secondes

    for scene in script_with_tts:
        narration = scene.get("narration", "").strip()
        if not narration:
            t_acc += scene.get("duration", 3.5)
            continue

        # Durée réelle du slide
        audio_path = scene.get("audio_path")
        if audio_path and Path(audio_path).exists():
            duration = get_video_duration(audio_path)
        else:
            duration = scene.get("duration", 3.5)
        duration = max(duration, 1.0)

        t_start = t_acc
        t_end   = t_acc + duration - 0.1

        # Formater en temps ASS (h:mm:ss.cc)
        def fmt(sec):
            h  = int(sec // 3600)
            m  = int((sec % 3600) // 60)
            s  = int(sec % 60)
            cs = int((sec - int(sec)) * 100)
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

        # Découper en lignes de max 45 chars
        words = narration.split()
        lines_text = []
        current = ""
        for w in words:
            if len(current) + len(w) + 1 <= 45:
                current = (current + " " + w).strip()
            else:
                if current:
                    lines_text.append(current)
                current = w
        if current:
            lines_text.append(current)

        text = "\\N".join(lines_text[:3])  # max 3 lignes avec \N (newline ASS)

        lines.append(f"Dialogue: 0,{fmt(t_start)},{fmt(t_end)},Default,,0,0,0,,{text}")
        t_acc += duration

    return "\n".join(lines)


def burn_subtitles(
    input_path: str,
    script_with_tts: list,
    output_path: str,
) -> bool:
    """
    Incruste les sous-titres sur la vidéo finale.
    Génère un fichier ASS (Advanced SubStation Alpha) temporaire,
    puis utilise ffmpeg ass filter pour l'incruster.
    """
    ffmpeg = _get_ffmpeg()
    out    = Path(output_path)
    inp    = Path(input_path)

    if not inp.exists():
        logging.error(f"[SUB] Fichier source introuvable: {input_path}")
        return False

    # Générer le fichier ASS
    ass_content = _build_ass(script_with_tts)
    if not ass_content.strip():
        logging.warning("[SUB] Aucun sous-titre généré")
        # Copier sans sous-titres
        import shutil
        shutil.copy2(input_path, output_path)
        return True

    ass_path = out.parent / f"_subs_{out.stem}.ass"
    ass_path.write_text(ass_content, encoding="utf-8")

    # Utiliser le filtre 'ass' (compatible avec libass + format ASS)
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")

    cmd = [
        ffmpeg, "-y",
        "-i", str(inp),
        "-vf", f"ass='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(out)
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    ass_path.unlink(missing_ok=True)

    if r.returncode == 0 and out.exists():
        size = out.stat().st_size / 1024 / 1024
        logging.info(f"[SUB] OK -> {out.name} ({size:.1f} MB)")
        print(f"[SUB] Sous-titres incrustés -> {out.name}")
        return True
    else:
        logging.warning(f"[SUB] Échec: {r.stderr[-300:]}")
        # Fallback : copier sans sous-titres
        import shutil
        shutil.copy2(input_path, output_path)
        print(f"[SUB] Fallback (sans sous-titres) -> {out.name}")
        return True  # ne pas bloquer le pipeline
