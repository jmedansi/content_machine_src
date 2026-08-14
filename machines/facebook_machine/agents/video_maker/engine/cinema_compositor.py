# cinema_compositor.py -- Assemblage final scenes -> MP4 1080x1920
# Améliorations : cross-fade xfade entre slides + fade in/out musique
import logging
import subprocess
from pathlib import Path

FFMPEG_PATH = r"C:\ffmpeg\ffmpeg-8.1-essentials_build\bin\ffmpeg.exe"
W, H = 1080, 1920
FPS  = 30
XFADE_DURATION = 0.25  # secondes de cross-fade entre slides


def _get_ffmpeg():
    try:
        r = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True, shell=True)
        if r.returncode == 0:
            return r.stdout.strip().split("\n")[0].strip()
    except Exception:
        pass
    if Path(FFMPEG_PATH).exists():
        return FFMPEG_PATH
    return "ffmpeg"


def _get_ffprobe():
    ffmpeg = _get_ffmpeg()
    if ffmpeg.endswith("ffmpeg.exe"):
        return ffmpeg.replace("ffmpeg.exe", "ffprobe.exe")
    elif ffmpeg.endswith("ffmpeg"):
        return ffmpeg.replace("ffmpeg", "ffprobe")
    try:
        r = subprocess.run(["where", "ffprobe"], capture_output=True, text=True, shell=True)
        if r.returncode == 0:
            return r.stdout.strip().split("\n")[0].strip()
    except Exception:
        pass
    ffprobe_path = FFMPEG_PATH.replace("ffmpeg.exe", "ffprobe.exe")
    if Path(ffprobe_path).exists():
        return ffprobe_path
    return "ffprobe"


def get_video_duration(path: str) -> float:
    """Retourne la durée d'une vidéo en secondes via ffprobe."""
    ffmpeg = _get_ffmpeg()
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    if not Path(ffprobe).exists():
        ffprobe = "ffprobe"
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _concat_with_xfade(scene_paths: list, output: Path, ffmpeg: str) -> bool:
    """
    Concatene les scenes avec cross-fade xfade entre chaque transition.
    Retourne True si succès.
    """
    if len(scene_paths) == 1:
        # Un seul clip : juste copier
        cmd = [ffmpeg, "-y", "-i", scene_paths[0],
               "-c:v", "libx264", "-preset", "fast", "-crf", "18",
               "-pix_fmt", "yuv420p", "-an", str(output)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode == 0

    # Récupérer les durées de chaque clip
    durations = [get_video_duration(p) for p in scene_paths]

    # Construire le filter_complex xfade en chaîne
    cmd = [ffmpeg, "-y"]
    for p in scene_paths:
        cmd += ["-i", p]

    # Construire les filtres
    filter_parts = []
    # Renommer les streams vidéo en [v0], [v1]...
    for i in range(len(scene_paths)):
        filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS,fps={FPS},scale={W}:{H}[v{i}]")

    # Chaîne de xfade
    current_label = "v0"
    offset_acc = 0.0
    for i in range(1, len(scene_paths)):
        offset_acc += max(durations[i - 1] - XFADE_DURATION, 0.1)
        next_label = f"v{i}"
        out_label  = f"xf{i}"
        filter_parts.append(
            f"[{current_label}][{next_label}]xfade=transition=fade:"
            f"duration={XFADE_DURATION}:offset={offset_acc:.3f}[{out_label}]"
        )
        current_label = out_label

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{current_label}]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output)
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # Fallback : concat simple sans xfade
        logging.warning(f"[COMP] xfade échoué, fallback concat simple: {r.stderr[-200:]}")
        return _concat_simple(scene_paths, output, ffmpeg)
    return output.exists()


def _concat_simple(scene_paths: list, output: Path, ffmpeg: str) -> bool:
    """Fallback concat sans transition."""
    concat_file = output.parent / "_concat_list.txt"
    concat_file.write_text(
        "\n".join(f"file '{Path(p).resolve().as_posix()}'" for p in scene_paths),
        encoding="utf-8"
    )
    cmd = [
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-an",
        str(output)
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    concat_file.unlink(missing_ok=True)
    return r.returncode == 0 and output.exists()


def concat_scenes(
    scene_paths: list,
    output_path: str,
    music_path: str = None,
    tts_path: str = None,
    music_volume: float = 0.20,
    tts_volume: float = 1.0,
    xfade: bool = True,
) -> bool:
    """
    Concatene les scènes MP4 avec cross-fade + mix audio (musique fond + voix TTS).

    scene_paths  : liste de chemins MP4 (dans l'ordre)
    music_path   : musique de fond (loop automatique)
    tts_path     : voix TTS globale ou None (si chaque scène a déjà son audio)
    music_volume : volume musique (0-1), fade in 1s + fade out 1.5s
    tts_volume   : volume voix (0-1)
    xfade        : activer cross-fade entre slides (défaut True)
    """
    ffmpeg = _get_ffmpeg()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    valid = [p for p in scene_paths if Path(p).exists()]
    if not valid:
        print("[COMP] Aucune scène valide trouvée")
        return False

    print(f"[COMP] Assemblage de {len(valid)} scènes (xfade={'ON' if xfade else 'OFF'})...")

    # Vérifier si les scènes ont déjà l'audio muxé dedans
    first_scene_has_audio = False
    if valid:
        ffprobe = _get_ffprobe()
        r = subprocess.run(
            [ffprobe, "-v", "error",
             "-select_streams", "a", "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1:nokey=1", valid[0]],
            capture_output=True, text=True
        )
        first_scene_has_audio = "audio" in r.stdout

    # Step 1 : Concat vidéo (avec ou sans xfade)
    raw_concat = out.parent / "_raw_concat.mp4"

    if xfade and len(valid) > 1:
        ok_concat = _concat_with_xfade(valid, raw_concat, ffmpeg)
    else:
        ok_concat = _concat_simple(valid, raw_concat, ffmpeg)

    if not ok_concat or not raw_concat.exists():
        print("[COMP] Concat vidéo échouée")
        return False

    total_duration = get_video_duration(str(raw_concat))
    print(f"[COMP] Concat OK ({raw_concat.stat().st_size / 1024 / 1024:.1f} MB, {total_duration:.1f}s)")

    # Step 2 : Audio mix
    has_music = music_path and Path(music_path).exists()
    has_tts   = tts_path and Path(tts_path).exists()

    if not has_music and not has_tts and not first_scene_has_audio:
        raw_concat.rename(out)
        print(f"[COMP] OK (pas d'audio global) -> {out.name}")
        return True

    # Step 2b : Pré-extraire l'audio des scènes en un seul fichier
    scenes_audio_path = None
    if first_scene_has_audio:
        scenes_audio_path = out.parent / "_scenes_audio.wav"
        # Concat audio des scènes via concat demuxer (rapide)
        audio_list = out.parent / "_audio_list.txt"
        audio_list.write_text(
            "\n".join(f"file '{Path(p).resolve().as_posix()}'" for p in valid),
            encoding="utf-8"
        )
        r_audio = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0",
             "-i", str(audio_list), "-vn",
             "-ac", "1", "-ar", "44100",
             str(scenes_audio_path)],
            capture_output=True, text=True
        )
        audio_list.unlink(missing_ok=True)
        if r_audio.returncode != 0 or not scenes_audio_path.exists():
            logging.warning(f"[COMP] Extraction audio scènes échouée: {r_audio.stderr[-200:]}")
            scenes_audio_path = None

    # Construire le mix audio final
    # L'input 0 est le raw_concat (vidéo sans audio)
    cmd = [ffmpeg, "-y", "-i", str(raw_concat)]
    filter_parts = []
    audio_inputs = 1

    if scenes_audio_path:
        cmd += ["-i", str(scenes_audio_path)]
        filter_parts.append(f"[{audio_inputs}:a]volume=1.0[scenes_mix]")
        audio_inputs += 1

    if has_tts:
        cmd += ["-i", tts_path]
        filter_parts.append(f"[{audio_inputs}:a]volume={tts_volume}[tts]")
        audio_inputs += 1

    if has_music:
        cmd += ["-i", music_path]
        # Loop musique + fade in 1s + fade out 1.5s
        fade_out_start = max(total_duration - 1.5, 0)
        filter_parts.append(
            f"[{audio_inputs}:a]"
            f"aloop=loop=-1:size=2e+09,"
            f"volume={music_volume},"
            f"afade=t=in:ss=0:d=1.0,"
            f"afade=t=out:st={fade_out_start:.2f}:d=1.5"
            f"[mus]"
        )
        audio_inputs += 1

    # Mix final audio
    to_mix = []
    if scenes_audio_path:
        to_mix.append("[scenes_mix]")
    if has_tts:
        to_mix.append("[tts]")
    if has_music:
        to_mix.append("[mus]")

    amap = ""
    if len(to_mix) > 1:
        joined_mix = "".join(to_mix)
        filter_parts.append(f"{joined_mix}amix=inputs={len(to_mix)}:duration=first:dropout_transition=2[aout]")
        amap = "[aout]"
    elif len(to_mix) == 1:
        filter_parts.append(f"{to_mix[0]}acopy[aout]")
        amap = "[aout]"

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v:0",
        "-map", amap,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        # PAS de -shortest : xfade réduit la vidéo de (n-1)*XFADE_DURATION mais l'audio
        # extrait des scènes reste à la durée totale. -shortest coupait les dernières
        # secondes de voix. Sans -shortest, la dernière frame est maintenue le temps
        # que le narrateur finisse de parler.
        "-movflags", "+faststart",
        str(out)
    ]

    r2 = subprocess.run(cmd, capture_output=True, text=True)
    raw_concat.unlink(missing_ok=True)
    if scenes_audio_path:
        scenes_audio_path.unlink(missing_ok=True)

    if r2.returncode == 0 and out.exists():
        size = out.stat().st_size / 1024 / 1024
        print(f"[COMP] OK -> {out.name} ({size:.1f} MB)")
        logging.info(f"[COMP] Final: {out.name} ({size:.1f} MB)")
        return True
    else:
        print(f"[COMP] Mix échoué: {r2.stderr[-300:]}")
        return False
