# gsap_renderer.py -- Elements UI animes via GSAP + Playwright -> MP4
# Supporte: cards flip, stat cards, UI mockup, Lottie player, bubble speech
import json
import logging
import shutil
import subprocess
import logging
import concurrent.futures
from pathlib import Path

W, H = 1080, 1920


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


def _webm_to_mp4(webm: Path, mp4: Path, audio_path: str = None) -> bool:
    ffmpeg = _get_ffmpeg()
    if audio_path and Path(audio_path).exists():
        cmd = [ffmpeg, "-y", "-i", str(webm), "-i", audio_path,
               "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "libx264", "-preset", "fast", "-crf", "18",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
               "-shortest", "-movflags", "+faststart", str(mp4)]
    else:
        cmd = [ffmpeg, "-y", "-i", str(webm),
               "-c:v", "libx264", "-preset", "fast", "-crf", "18",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and mp4.exists()


def _playwright_record(html_content: str, duration: float, output_mp4: str,
                        audio_path: str = None) -> bool:
    # Exécuter dans un thread séparé pour éviter les conflits asyncio
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_playwright_record_sync, html_content, duration, output_mp4, audio_path)
        return future.result()


def _playwright_record_sync(html_content: str, duration: float, output_mp4: str,
                            audio_path: str = None) -> bool:
    from playwright.sync_api import sync_playwright

    out = Path(output_mp4)
    out.parent.mkdir(parents=True, exist_ok=True)
    html_file = out.parent / f"_gsap_{out.stem}.html"
    html_file.write_text(html_content, encoding="utf-8")

    video_dir = out.parent / f"_pw_{out.stem}"
    video_dir.mkdir(exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-web-security",
                      "--allow-file-access-from-files"]
            )
            ctx = browser.new_context(
                viewport={"width": W, "height": H},
                record_video_dir=str(video_dir),
                record_video_size={"width": W, "height": H},
            )
            page = ctx.new_page()
            file_path = html_file.absolute().as_posix()
            page.goto(f"file:///{file_path}", wait_until="load")
            page.wait_for_timeout(int((duration + 1.0) * 1000))
            ctx.close()
            browser.close()
    except Exception as e:
        logging.error(f"[GSAP] Playwright error: {e}")
        return False

    webms = list(video_dir.glob("*.webm"))
    if not webms:
        return False
    webm = max(webms, key=lambda f: f.stat().st_mtime)
    ok = _webm_to_mp4(webm, out, audio_path)
    shutil.rmtree(video_dir, ignore_errors=True)
    html_file.unlink(missing_ok=True)
    return ok


# ── SCENE TYPES ────────────────────────────────────────────────


def render_stat_cards(
    cards: list,
    output_path: str,
    duration: float = 5.0,
    theme: dict = None,
    audio_path: str = None,
) -> bool:
    """
    Cards B2B qui apparaissent avec animation spring + icone.
    cards = [
      {"value": "+127%", "label": "Croissance"},
      ...
    ]
    """
    if theme is None:
        from scene_sequencer import THEMES
        theme = THEMES["white"]

    bg       = theme.get("bg", "#f8fafc")
    text_c   = theme.get("text", "#0f172a")
    accent   = theme.get("accent", "#d4af37")
    card_bg  = "#ffffff" if bg == "#f8fafc" else "#0c1a3a"
    card_brd = "#e2e8f0" if bg == "#f8fafc" else "#1e3a5f"
    lbl_c    = "#64748b" if bg == "#f8fafc" else "#94a3b8"

    cards_json = json.dumps(cards)
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1920px; background:{bg};
  font-family:'Segoe UI',system-ui,sans-serif;
  display:flex; flex-direction:column; justify-content:center;
  align-items:center; gap:40px; overflow:hidden; }}

.title {{ color:{text_c}; font-size:64px; font-weight:900;
  text-align:center; padding:0 60px; margin-bottom:20px;
  opacity:0; transform:translateY(-40px); }}

.card {{ width:900px; background:{card_bg};
  border:2px solid {card_brd}; border-radius:24px;
  padding:52px 60px; display:flex; align-items:center; gap:48px;
  opacity:0; transform:translateX(-80px);
  box-shadow: 0 8px 40px rgba(0,0,0,0.08); }}

.card-icon {{ font-size:80px; flex-shrink:0; }}

.card-value {{ color:{accent}; font-size:88px; font-weight:900;
  line-height:1; }}

.card-label {{ color:{lbl_c}; font-size:32px; font-weight:500;
  margin-top:8px; }}
</style>
</head><body>
<div class="title" id="title">Resultats</div>
<div id="cards"></div>
<script>
const data = {cards_json};
const container = document.getElementById('cards');
container.style.cssText = 'display:flex;flex-direction:column;gap:36px;width:100%;padding:0 90px;';

const icons = ['TrendingUp','Users','DollarSign','Zap','Star','Target'];
const emojis = ['📈','👥','💰','⚡','⭐','🎯'];

data.forEach((d, i) => {{
  const card = document.createElement('div');
  card.className = 'card';
  card.id = 'card' + i;
  card.innerHTML = `
    <div class="card-icon">${{emojis[i % emojis.length]}}</div>
    <div>
      <div class="card-value">${{d.value}}</div>
      <div class="card-label">${{d.label}}</div>
    </div>`;
  container.appendChild(card);
}});

gsap.to('#title', {{
  opacity:1, y:0, duration:0.8, ease:'back.out(1.7)', delay:0.3
}});

data.forEach((_, i) => {{
  gsap.to('#card' + i, {{
    opacity:1, x:0, duration:0.7,
    ease:'back.out(1.4)',
    delay: 0.6 + i * 0.25
  }});
}});
</script>
</body></html>"""
    return _playwright_record(html, duration, output_path, audio_path)


def render_speech_bubble(
    character_emoji: str,
    bubble_text: str,
    output_path: str,
    duration: float = 4.0,
    theme: dict = None,
    audio_path: str = None,
) -> bool:
    """
    Personnage emoji + bulle de dialogue animee.
    """
    if theme is None:
        from scene_sequencer import THEMES
        theme = THEMES["white"]

    bg     = theme.get("bg", "#f8fafc")
    accent = theme.get("accent", "#d4af37")
    bubble_bg  = "#ffffff" if bg == "#f8fafc" else "#1e293b"
    bubble_txt = "#0f172a" if bg == "#f8fafc" else "#f8fafc"
    arrow_c    = bubble_bg

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1920px; background:{bg};
  font-family:'Segoe UI',system-ui,sans-serif;
  display:flex; flex-direction:column; justify-content:center;
  align-items:center; gap:60px; overflow:hidden; }}

.character {{ font-size:280px; opacity:0; transform:scale(0.5);
  filter:drop-shadow(0 10px 30px rgba(0,0,0,0.15)); }}

.bubble-wrap {{ position:relative; opacity:0; transform:translateY(60px); }}

.bubble {{ background:{bubble_bg}; border-radius:40px; padding:60px 80px;
  max-width:860px; position:relative;
  border: 2px solid #e2e8f0;
  box-shadow: 0 12px 50px rgba(0,0,0,0.10); }}

.bubble::before {{ content:''; position:absolute;
  top:-40px; left:50%; transform:translateX(-50%);
  border:20px solid transparent;
  border-bottom-color:{arrow_c}; }}

.bubble-text {{ color:{bubble_txt}; font-size:64px; font-weight:800;
  line-height:1.2; text-align:center; }}

.brand {{ color:{accent}; font-size:28px; font-weight:700;
  letter-spacing:3px; text-transform:uppercase;
  position:absolute; bottom:100px; opacity:0; }}
</style>
</head><body>
<div class="bubble-wrap" id="bubble">
  <div class="bubble">
    <div class="bubble-text">{bubble_text}</div>
  </div>
</div>
<div class="character" id="char">{character_emoji}</div>
<div class="brand" id="brand">IncidenX</div>
<script>
const tl = gsap.timeline();
tl.to('#char', {{ opacity:1, scale:1, duration:0.8, ease:'back.out(1.7)', delay:0.2 }})
  .to('#bubble', {{ opacity:1, y:0, duration:0.7, ease:'back.out(1.4)' }}, '-=0.3')
  .to('#brand', {{ opacity:1, duration:0.5 }}, '+=0.5');
</script>
</body></html>"""
    return _playwright_record(html, duration, output_path, audio_path)


def render_ui_mockup(
    title: str,
    features: list,
    output_path: str,
    duration: float = 5.0,
    theme: dict = None,
    audio_path: str = None,
) -> bool:
    """
    Mockup d'interface/app qui se construit element par element.
    features = ["Tableau de bord en temps reel", "Rapports automatiques", ...]
    """
    if theme is None:
        from scene_sequencer import THEMES
        theme = THEMES["white"]

    bg      = theme.get("bg", "#f8fafc")
    text_c  = theme.get("text", "#0f172a")
    accent  = theme.get("accent", "#d4af37")
    phone_bg   = "#ffffff" if bg == "#f8fafc" else "#0f172a"
    phone_brd  = "#e2e8f0" if bg == "#f8fafc" else "#1e3a5f"
    row_bg     = "#f1f5f9" if bg == "#f8fafc" else "#0c1a3a"
    feat_txt   = "#0f172a" if bg == "#f8fafc" else "#f8fafc"

    features_json = json.dumps(features)
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1920px; background:{bg};
  font-family:'Segoe UI',system-ui,sans-serif;
  display:flex; flex-direction:column; justify-content:center;
  align-items:center; padding:80px; gap:48px; overflow:hidden; }}

.phone {{ width:700px; background:{phone_bg}; border-radius:48px;
  border:3px solid {phone_brd}; padding:0; overflow:hidden;
  box-shadow: 0 20px 60px rgba(0,0,0,0.12);
  opacity:0; transform:scale(0.8) translateY(60px); }}

.phone-bar {{ background:{row_bg}; padding:24px 40px;
  display:flex; justify-content:space-between; align-items:center; }}

.phone-title {{ color:{accent}; font-size:32px; font-weight:700; }}
.phone-dot {{ width:12px; height:12px; border-radius:50%; background:#22c55e; }}

.phone-body {{ padding:32px 36px; display:flex; flex-direction:column; gap:20px; }}

.feature-row {{ background:{row_bg}; border-radius:16px; padding:28px 32px;
  display:flex; align-items:center; gap:24px;
  border-left:4px solid {accent};
  opacity:0; transform:translateX(-40px); }}

.feat-icon {{ font-size:44px; flex-shrink:0; }}
.feat-text {{ color:{feat_txt}; font-size:30px; font-weight:600; line-height:1.2; }}

.headline {{ color:{text_c}; font-size:68px; font-weight:900;
  text-align:center; line-height:1.15;
  opacity:0; transform:translateY(-30px); }}
</style>
</head><body>
<div class="headline" id="hl">{title}</div>
<div class="phone" id="phone">
  <div class="phone-bar">
    <div class="phone-title">Dashboard</div>
    <div class="phone-dot"></div>
  </div>
  <div class="phone-body" id="feats"></div>
</div>
<script>
const feats = {features_json};
const emojis = ['📊','🚀','💡','⚡','🎯','📈','✅','🔥'];
const container = document.getElementById('feats');
feats.forEach((f, i) => {{
  const row = document.createElement('div');
  row.className = 'feature-row';
  row.id = 'feat' + i;
  row.innerHTML = `<div class="feat-icon">${{emojis[i % emojis.length]}}</div>
                   <div class="feat-text">${{f}}</div>`;
  container.appendChild(row);
}});

const tl = gsap.timeline();
tl.to('#hl', {{ opacity:1, y:0, duration:0.8, ease:'back.out(1.4)', delay:0.3 }})
  .to('#phone', {{ opacity:1, scale:1, y:0, duration:0.9, ease:'back.out(1.2)' }}, '-=0.2');

feats.forEach((_, i) => {{
  tl.to('#feat' + i, {{ opacity:1, x:0, duration:0.5, ease:'power2.out' }},
        i === 0 ? '+=0.1' : '-=0.2');
}});
</script>
</body></html>"""
    return _playwright_record(html, duration, output_path, audio_path)


def render_lottie_scene(
    lottie_url: str,
    caption: str,
    output_path: str,
    duration: float = 4.0,
    audio_path: str = None,
) -> bool:
    """
    Joue une animation Lottie depuis une URL publique (LottieFiles CDN) ou locale.
    lottie_url: URL directe vers un fichier .json Lottie
    """
    src_attr = f'src="{lottie_url}"'
    inline_script = ""
    if lottie_url and lottie_url.startswith("file:///"):
        try:
            import urllib.request
            fpath = urllib.request.url2pathname(lottie_url.replace("file:///", ""))
            with open(fpath, "r", encoding="utf-8") as f:
                lottie_data = f.read()
            src_attr = ""
            inline_script = f"document.getElementById('lottie').load({lottie_data});"
        except Exception as e:
            pass

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://unpkg.com/@lottiefiles/lottie-player@1.5.7/dist/lottie-player.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1920px; background:#020617;
  font-family:'Segoe UI',system-ui,sans-serif;
  display:flex; flex-direction:column; justify-content:center;
  align-items:center; gap:60px; overflow:hidden; }}

lottie-player {{ width:800px; height:800px; opacity:0; transform:scale(0.7); }}

.caption {{ color:#f8fafc; font-size:72px; font-weight:900;
  text-align:center; padding:0 80px; line-height:1.2;
  opacity:0; transform:translateY(40px); }}

.gold {{ color:#d4af37; }}
</style>
</head><body>
<lottie-player id="lottie" {src_attr} background="transparent"
  speed="1" loop autoplay></lottie-player>
<div class="caption" id="cap">{caption}</div>
<script>
{inline_script}
gsap.to('#lottie', {{ opacity:1, scale:1, duration:0.9, ease:'back.out(1.4)', delay:0.4 }});
gsap.to('#cap', {{ opacity:1, y:0, duration:0.8, ease:'power2.out', delay:1.0 }});
</script>
</body></html>"""
    return _playwright_record(html, duration, output_path, audio_path)


def render_hook_text(
    text: str,
    output_path: str,
    duration: float = 2.0,
    theme: dict = None,
    entrance: str = "bottom",
    audio_path: str = None,
) -> bool:
    """
    Slide hook plein ecran - texte massif, impact maximal.
    Fond sombre ou blanc selon le theme.
    """
    if theme is None:
        from scene_sequencer import THEMES
        theme = THEMES["dark"]

    bg = theme.get("gradient") or theme.get("bg", "#020617")
    bg_css = f"background: {bg};" if not bg.startswith("linear") else f"background: {bg};"
    text_color = theme.get("text", "#f8fafc")
    accent = theme.get("accent", "#d4af37")

    entrances = {
        "bottom": "translateY(80px)",
        "left":   "translateX(-80px)",
        "right":  "translateX(80px)",
        "top":    "translateY(-80px)",
    }
    transform_from = entrances.get(entrance, "translateY(80px)")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1920px; {bg_css}
  font-family:'Segoe UI',system-ui,sans-serif;
  display:flex; flex-direction:column; justify-content:center;
  align-items:center; overflow:hidden; position:relative; }}
.word-wrap {{ display:flex; flex-direction:column; align-items:center;
  gap:16px; padding:0 80px; text-align:center; }}
.word {{ color:{text_color}; font-size:112px; font-weight:900;
  line-height:1.05; letter-spacing:-2px;
  opacity:0; transform:{transform_from}; }}
.accent-bar {{ width:0; height:5px;
  background:linear-gradient(90deg,{accent},{accent}aa,{accent});
  border-radius:3px; margin-top:24px; }}
.brand {{ position:absolute; top:68px; right:80px;
  color:{accent}; font-size:22px; font-weight:700;
  letter-spacing:3px; text-transform:uppercase; opacity:0; }}
</style>
</head><body>
<div class="word-wrap" id="wrap">
  <div class="word" id="txt">{text}</div>
  <div class="accent-bar" id="bar"></div>
</div>
<div class="brand" id="brand">IncidenX</div>
<script>
const tl = gsap.timeline();
tl.to('#txt', {{ opacity:1, x:0, y:0, duration:0.6,
                ease:'back.out(1.7)', delay:0.2 }})
  .to('#bar', {{ width:'220px', duration:0.5, ease:'power2.out' }}, '-=0.1')
  .to('#brand', {{ opacity:1, duration:0.4 }}, '-=0.2');
</script>
</body></html>"""
    return _playwright_record(html, duration, output_path, audio_path)


def render_cta(
    text: str,
    output_path: str,
    duration: float = 3.5,
    theme: dict = None,
    audio_path: str = None,
) -> bool:
    """
    Scene CTA finale - fond contrastant or/jaune, texte sombre.
    """
    if theme is None:
        from scene_sequencer import THEMES
        theme = THEMES["contrast"]

    bg = theme.get("gradient") or theme.get("bg", "#d4af37")
    bg_css = f"background: {bg};"
    text_color = theme.get("text", "#020617")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1920px; {bg_css}
  font-family:'Segoe UI',system-ui,sans-serif;
  display:flex; flex-direction:column; justify-content:center;
  align-items:center; gap:48px; overflow:hidden; }}
.cta-text {{ color:{text_color}; font-size:92px; font-weight:900;
  text-align:center; padding:0 80px; line-height:1.15;
  opacity:0; transform:translateY(60px); }}
.cta-sub {{ color:{text_color}aa; font-size:40px; font-weight:600;
  text-align:center; padding:0 100px; line-height:1.4;
  opacity:0; }}
.arrow {{ font-size:100px; opacity:0; transform:translateY(-20px); }}
</style>
</head><body>
<div class="arrow" id="arrow">👇</div>
<div class="cta-text" id="txt">{text}</div>
<div class="cta-sub" id="sub">IncidenX</div>
<script>
const tl = gsap.timeline();
tl.to('#txt', {{ opacity:1, y:0, duration:0.7, ease:'back.out(1.4)', delay:0.3 }})
  .to('#arrow', {{ opacity:1, y:0, duration:0.5, ease:'bounce.out' }}, '-=0.2')
  .to('#sub', {{ opacity:1, duration:0.5 }}, '+=0.2');

// Pulse arrow
gsap.to('#arrow', {{
  y: 15, duration:0.6, ease:'power1.inOut',
  repeat:-1, yoyo:true, delay:1.2
}});
</script>
</body></html>"""
    return _playwright_record(html, duration, output_path, audio_path)


if __name__ == "__main__":
    import os
    os.makedirs("d:/Content_Machine/machines/facebook-machine/temp", exist_ok=True)

    print("Test 1: stat cards...")
    render_stat_cards(
        cards=[
            {"value": "+127%", "label": "Revenus en 90 jours"},
            {"value": "3x",    "label": "Plus de clients"},
            {"value": "0 XOF", "label": "Investissement requis"},
        ],
        output_path="d:/Content_Machine/machines/facebook-machine/temp/test_cards.mp4",
        duration=5.0,
    )

    print("Test 2: speech bubble...")
    render_speech_bubble(
        character_emoji="🧑‍💼",
        bubble_text="En 30 jours, j'ai triplé mes tarifs et personne n'a refusé.",
        output_path="d:/Content_Machine/machines/facebook-machine/temp/test_bubble.mp4",
        duration=4.0,
    )

    print("Test 3: UI mockup...")
    render_ui_mockup(
        title="La methode qui change tout",
        features=["Positionnement premium", "Clients qui viennent a toi", "Tarifs non-negociables"],
        output_path="d:/Content_Machine/machines/facebook-machine/temp/test_ui.mp4",
        duration=5.0,
    )
