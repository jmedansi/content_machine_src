# scene_director.py -- Orchestrateur Cinema Machine
# Prend un script de scenes JSON et produit un MP4 final complet
#
# FORMAT SCRIPT:
# [
#   {
#     "type": "image_text",       # image + texte anime
#     "image_path": "...",
#     "text": "Tu factures trop peu ?",
#     "narration": "Est-ce que tu factures a ta juste valeur ?",
#     "duration": 3.5
#   },
#   {
#     "type": "bar_chart",
#     "title": "Croissance des revenus",
#     "data": [{"label":"Freelance","start":5,"end":85}, ...],
#     "narration": "Regarde la difference.",
#     "duration": 4.0
#   },
#   {
#     "type": "stat_counter",
#     "stats": [{"label":"Clients","value":127,"suffix":"+"}],
#     "narration": "Plus de cent vingt sept nouveaux clients.",
#     "duration": 3.5
#   },
#   {
#     "type": "line_chart",
#     "series": [{"label":"Revenus","x":[1,2,3],"y":[10,30,80]}],
#     "title": "Progression",
#     "narration": "La courbe ne ment pas.",
#     "duration": 4.0
#   },
#   {
#     "type": "stat_cards",
#     "cards": [{"value":"+127%","label":"Revenus"}],
#     "narration": "Les resultats parlent.",
#     "duration": 5.0
#   },
#   {
#     "type": "speech_bubble",
#     "character": "man_office",     # emoji ou unicode
#     "text": "En 30 jours j'ai triple mes tarifs.",
#     "narration": "Voici ce qu'ils disent.",
#     "duration": 4.0
#   },
#   {
#     "type": "ui_mockup",
#     "title": "La methode qui change tout",
#     "features": ["Positionnement premium", "Clients qualifies"],
#     "narration": "Voici comment ca fonctionne.",
#     "duration": 5.0
#   },
#   {
#     "type": "lottie",
#     "url": "https://assets10.lottiefiles.com/packages/lf20_jcikwtux.json",
#     "caption": "C'est le moment d'agir.",
#     "narration": "Ne laisse pas cette opportunite passer.",
#     "duration": 4.0
#   }
# ]

import sys
import subprocess
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from tts_engine import synthesize_segments
from chart_renderer import render_bar_chart_race, render_line_chart, render_stat_counter
from gsap_renderer import (render_stat_cards, render_speech_bubble, render_ui_mockup,
                            render_lottie_scene, render_hook_text, render_cta)
from slide_renderer import render_slide
from cinema_compositor import concat_scenes

MUSIC_DIR = Path(__file__).parent.parent / "assets/music"

CHARACTER_EMOJIS = {
    "man_office":   "🧑\u200d💼",
    "woman_office": "👩\u200d💼",
    "man":          "🙋\u200d♂️",
    "woman":        "🙋\u200d♀️",
    "boss":         "👔",
    "thinking":     "🤔",
    "money":        "🤑",
    "star":         "🌟",
}


def _get_music() -> str | None:
    for ext in ("*.mp3", "*.wav", "*.aac"):
        tracks = list(MUSIC_DIR.glob(ext))
        if tracks:
            return str(tracks[0])
    return None


def _render_image_text_scene(scene: dict, out_path: str) -> bool:
    """Image + texte anime via Playwright GSAP. Supporte theme et entrance."""
    from gsap_renderer import _playwright_record
    from scene_sequencer import THEMES

    img_path = scene.get("image_path", "")
    text     = scene.get("text", "")
    duration = scene.get("duration", 3.5)
    theme    = scene.get("_theme") or THEMES["dark"]
    entrance = scene.get("_entrance", "bottom")

    entrances = {
        "bottom":   ("translateY(60px)", "y:0"),
        "left":     ("translateX(-80px)", "x:0"),
        "right":    ("translateX(80px)",  "x:0"),
        "top":      ("translateY(-60px)", "y:0"),
        "zoom_in":  ("scale(0.5)", "scale:1"),
        "fade":     ("opacity:0", "opacity:1"),
    }
    tfrom, tto = entrances.get(entrance, ("translateY(60px)", "y:0"))

    has_image = img_path and Path(img_path).exists()
    if has_image:
        img_url = "file:///" + Path(img_path).absolute().as_posix()
    else:
        img_url = ""

    accent = theme.get("accent", "#d4af37")

    if has_image:
        bg_body  = ""
        bg_extra = f"""
<div class="bg" style="background-image:url('{img_url}');background-size:cover;background-position:center;"></div>
<div class="overlay"></div>"""
        text_color  = "#f8fafc"
        content_pos = "position:absolute; bottom:140px; left:80px; right:80px;"
    else:
        bg = theme.get("gradient") or theme.get("bg", "#020617")
        bg_body  = f"background:{bg};"
        bg_extra = ""
        text_color  = theme.get("text", "#f8fafc")
        content_pos = "display:flex;justify-content:center;align-items:center;height:100%;padding:0 80px;text-align:center;"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1920px; overflow:hidden; position:relative;
  font-family:'Segoe UI',system-ui,sans-serif; {bg_body} }}
.bg {{ position:absolute; inset:0; }}
.overlay {{ position:absolute; inset:0;
  background:linear-gradient(to top,rgba(2,6,23,0.90) 0%,rgba(2,6,23,0.25) 50%,transparent 100%); }}
.accent {{ position:absolute; bottom:380px; left:80px; height:3px; width:0;
  background:linear-gradient(90deg,{accent},{accent}aa,{accent}); }}
.content {{ position:absolute; z-index:10; {content_pos} }}
.text {{ color:{text_color}; font-size:88px; font-weight:900; line-height:1.1;
  letter-spacing:-1px; opacity:0; transform:{tfrom}; }}
.brand {{ position:absolute; top:68px; right:80px;
  color:{accent}; font-size:22px; font-weight:700;
  letter-spacing:3px; text-transform:uppercase; z-index:20; opacity:0; }}
</style>
</head><body>
{bg_extra}
<div class="accent" id="line"></div>
<div class="content">
  <div class="text" id="txt">{text}</div>
</div>
<div class="brand" id="brand">IncidenX</div>
<script>
{'gsap.to(".bg", { scale:1.08, duration:' + str(duration) + ', ease:"none" });' if has_image else ''}
gsap.to('#line', {{ width:'180px', duration:0.5, ease:'power2.out', delay:0.4 }});
gsap.to('#txt', {{ opacity:1, {tto}, duration:0.7, ease:'back.out(1.4)', delay:0.5 }});
gsap.to('#brand', {{ opacity:1, duration:0.5, delay:0.8 }});
</script>
</body></html>"""
    return _playwright_record(html, duration, out_path)


def render_script(
    script: list,
    output_path: str,
    voice: str = "fr-FR-HenriNeural",
    music_path: str = None,
) -> bool:
    """
    Execute le script complet et produit le MP4 final.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    work_dir = out.parent / "_cinema_work"
    work_dir.mkdir(exist_ok=True)

    if music_path is None:
        music_path = _get_music()

    # Step 1: TTS narration — genere + mesure duree reelle par segment
    print(f"[DIRECTOR] Etape 1/3 : Voix TTS ({len(script)} segments)...")
    script_with_tts = synthesize_segments(script, str(work_dir / "tts"), voice=voice)

    # Caler la duree de chaque scene sur la duree TTS reelle + buffer
    from cinema_compositor import get_video_duration
    from sfx_engine import mix_sfx_with_tts, ensure_sfx_generated
    ensure_sfx_generated()

    for scene in script_with_tts:
        audio_path = scene.get("audio_path")
        if audio_path and Path(audio_path).exists():
            tts_dur = get_video_duration(audio_path)
            if tts_dur > 0.5:
                scene["duration"] = round(tts_dur + 1.2, 2)  # 1.2s buffer pour finir audio avant fin slide

    # Step 2: Render chaque scene
    print(f"[DIRECTOR] Etape 2/3 : Rendu scenes...")
    scene_paths = []

    for i, scene in enumerate(script_with_tts):
        stype = scene.get("type", "image_text")
        scene_out = str(work_dir / f"scene_{i:02d}_{stype}.mp4")
        duration = scene.get("duration", 3.5)
        ok = False

        # Mixer TTS + SFX pour cette scene
        raw_audio = scene.get("audio_path")
        mixed_audio = None
        if raw_audio and Path(raw_audio).exists():
            mixed_audio_path = str(work_dir / f"audio_mix_{i:02d}.aac")
            mixed_audio = mix_sfx_with_tts(raw_audio, stype, duration, mixed_audio_path)

        print(f"  Scene {i+1}/{len(script)}: {stype}...")

        theme    = scene.get("_theme")
        entrance = scene.get("_entrance", "bottom")

        if stype == "hook_text":
            ok = render_hook_text(
                text=scene.get("text", ""),
                output_path=scene_out,
                duration=duration,
                theme=theme,
                entrance=entrance,
            )

        elif stype == "cta":
            ok = render_cta(
                text=scene.get("text", ""),
                output_path=scene_out,
                duration=duration,
                theme=theme,
            )

        elif stype == "image_text":
            ok = _render_image_text_scene(scene, scene_out)

        elif stype == "bar_chart":
            ok = render_bar_chart_race(
                data=scene.get("data", []),
                output_path=scene_out,
                title=scene.get("title", ""),
                duration=duration,
                theme=theme,
            )

        elif stype == "line_chart":
            ok = render_line_chart(
                series=scene.get("series", []),
                output_path=scene_out,
                title=scene.get("title", ""),
                x_label=scene.get("x_label", ""),
                y_label=scene.get("y_label", ""),
                duration=duration,
            )

        elif stype == "stat_counter":
            ok = render_stat_counter(
                stats=scene.get("stats", []),
                output_path=scene_out,
                duration=duration,
            )

        elif stype == "stat_cards":
            ok = render_stat_cards(
                cards=scene.get("cards", []),
                output_path=scene_out,
                duration=duration,
                theme=theme,
            )

        elif stype == "speech_bubble":
            char_key = scene.get("character", "man_office")
            emoji = CHARACTER_EMOJIS.get(char_key, char_key)
            ok = render_speech_bubble(
                character_emoji=emoji,
                bubble_text=scene.get("text", ""),
                output_path=scene_out,
                duration=duration,
                theme=theme,
            )

        elif stype == "ui_mockup":
            ok = render_ui_mockup(
                title=scene.get("title", ""),
                features=scene.get("features", []),
                output_path=scene_out,
                duration=duration,
                theme=theme,
            )

        elif stype == "lottie":
            ok = render_lottie_scene(
                lottie_url=scene.get("url", ""),
                caption=scene.get("caption", ""),
                output_path=scene_out,
                duration=duration,
            )

        # Post-mux audio dans le MP4 de la scene si disponible
        if ok and mixed_audio and Path(mixed_audio).exists() and Path(scene_out).exists():
            scene_with_audio = scene_out.replace(".mp4", "_av.mp4")
            ffmpeg = _get_ffmpeg_path()
            r = subprocess.run([
                ffmpeg, "-y",
                "-i", scene_out,
                "-i", mixed_audio,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-movflags", "+faststart",
                scene_with_audio
            ], capture_output=True, text=True)
            if r.returncode == 0 and Path(scene_with_audio).exists():
                Path(scene_out).unlink(missing_ok=True)
                Path(scene_with_audio).rename(scene_out)

        if ok:
            scene_paths.append(scene_out)
            print(f"  OK: scene_{i:02d}")
        else:
            print(f"  FAIL: scene_{i:02d} ignoree")

    if not scene_paths:
        print("[DIRECTOR] Aucune scene generee.")
        return False

    # Step 3: Concat + mix audio
    print(f"[DIRECTOR] Etape 3/3 : Assemblage {len(scene_paths)} scenes + audio...")

    from cinema_compositor import concat_scenes
    ok = concat_scenes(
        scene_paths=scene_paths,
        output_path=output_path,
        music_path=music_path,
        tts_path=None,
        music_volume=0.20,
        tts_volume=1.0,
    )

    if ok:
        print(f"[DIRECTOR] SUCCES -> {out.name}")
    else:
        print("[DIRECTOR] ECHEC assemblage final")

    return ok


import subprocess

def generate_and_render(
    topic: str,
    output_path: str,
    voice: str = "fr-FR-HenriNeural",
    music_path: str = None,
    publish: bool = False,
    fb_description: str = None,
    persona: str = "",
) -> bool:
    """
    Pipeline simplifie : topic -> script AV -> slides fond blanc -> MP4.
    Utilise slide_renderer (templates propres) + TTS sync.
    """
    from script_generator import generate_av_script, script_to_av_format

    # 1. Generer le script (passer le persona pour choisir les bons REAL_PROOFS)
    script = generate_av_script(topic, persona=persona)
    if not script:
        print("[DIRECTOR] Echec generation script")
        return False

    print("\n" + script_to_av_format(script) + "\n")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    work_dir = out.parent / "_cinema_work"
    work_dir.mkdir(exist_ok=True)

    if music_path is None:
        music_path = _get_music()

    # 2. TTS par segment, calage duree reelle
    print(f"[DIRECTOR] TTS ({len(script)} segments)...")
    script_with_tts = synthesize_segments(script, str(work_dir / "tts"), voice=voice)

    from cinema_compositor import get_video_duration
    for scene in script_with_tts:
        ap = scene.get("audio_path")
        if ap and Path(ap).exists():
            d = get_video_duration(ap)
            if d > 0.5:
                scene["duration"] = round(d + 1.2, 2)  # 1.2s buffer pour finir audio avant fin slide

    # 3. Render chaque slide — audio mux directement dans le slide
    from sfx_engine import mix_sfx_with_tts, ensure_sfx_generated
    ensure_sfx_generated()

    print(f"[DIRECTOR] Rendu {len(script_with_tts)} slides...")
    scene_paths = []
    preview_dir = out.parent / "previews"
    preview_dir.mkdir(exist_ok=True)

    for i, scene in enumerate(script_with_tts):
        stype     = scene.get("type", "tip")
        scene_out = str(work_dir / f"scene_{i:02d}_{stype}.mp4")
        audio     = scene.get("audio_path")
        duration  = scene.get("duration", 3.5)
        preview   = str(preview_dir / f"slide_{i:02d}_{stype}.jpg")

        print(f"  Slide {i+1}/{len(script_with_tts)}: {stype} — {scene.get('title','')[:45]}...")

        # Mixer TTS + SFX
        if audio and Path(audio).exists():
            mixed_audio = str(work_dir / f"audio_mix_{i:02d}.aac")
            audio = mix_sfx_with_tts(audio, stype, duration, mixed_audio)

        ok = render_slide(scene, scene_out, audio_path=audio, preview_path=preview)
        if ok:
            scene_paths.append(scene_out)
            print(f"  OK  (preview: previews/slide_{i:02d}_{stype}.jpg)")
        else:
            print(f"  FAIL — slide ignoree")

    if not scene_paths:
        print("[DIRECTOR] Aucun slide genere.")
        return False

    # 5. Assemblage final
    print(f"[DIRECTOR] Assemblage {len(scene_paths)} scenes...")
    ok = concat_scenes(
        scene_paths=scene_paths,
        output_path=output_path,
        music_path=music_path,
        tts_path=None,
        music_volume=0.22,
        tts_volume=1.0,
    )

    if not ok:
        print("[DIRECTOR] ECHEC assemblage")
        return False

    # 6. Sous-titres burned-in (DÉSACTIVÉ - plus de texte affiché)
    # from subtitle_engine import burn_subtitles
    # subbed = str(out.parent / f"{out.stem}_subbed.mp4")
    # ok_sub = burn_subtitles(output_path, script_with_tts, subbed)
    # if ok_sub and Path(subbed).exists():
    #     Path(output_path).unlink(missing_ok=True)
    #     Path(subbed).rename(output_path)
    #     print(f"[DIRECTOR] Sous-titres incrustés")

    print(f"[DIRECTOR] SUCCES -> {out.name}")

    # 7. Publication Facebook (optionnel)
    if publish:
        from facebook_publisher import publish_reel
        desc = fb_description or f"{topic}\n\n#Facebook #IncidenX #Motivation"
        publish_reel(output_path, title=topic, description=desc)

    return True


def _get_ffmpeg_path():
    from cinema_compositor import _get_ffmpeg
    return _get_ffmpeg()


if __name__ == "__main__":
    generate_and_render(
        topic=(
            "Comment les freelances africains peuvent tripler leurs tarifs "
            "en 30 jours sans perdre leurs clients"
        ),
        output_path="d:/Content_Machine/machines/facebook-machine/temp/cinema_av_demo.mp4",
    )
