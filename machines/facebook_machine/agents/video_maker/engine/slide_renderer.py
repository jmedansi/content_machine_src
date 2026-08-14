# slide_renderer.py -- Slides fond blanc, titre + sous-titre + Lottie + audio mux
# Ameliorations : Poppins locale, attente Lottie chargee avant enregistrement

import shutil
import subprocess
import logging
import asyncio
import concurrent.futures
from pathlib import Path

FFMPEG_PATH = r"C:\ffmpeg\ffmpeg-8.1-essentials_build\bin\ffmpeg.exe"
FONTS_DIR   = Path(__file__).parent.parent / "assets" / "fonts"
W, H = 1080, 1920

# ── Zones de placement fixes (px, viewport 1080×1920) ───────────────────────
# Le texte est toujours positionné à partir du haut (固定)
# Le numéro est positionné au-dessus du texte
LOTTIE_TOP      = 80    # bord haut du bloc lottie (px)
TIP_NUM_TOP     = 820   # numéro watermark tip layout "top" (px)
TEXT_TOP        = 960   # bord haut zone texte — TOUJOURS à cette hauteur (px = 50% de 1920)
TEXT_BOTTOM     = 80    # marge basse fixe — texte jamais en dessous de 1920-80=1840px


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


def _font_face_css() -> str:
    """Génère le bloc @font-face Poppins depuis les fichiers locaux."""
    variants = [
        ("Poppins-Black.ttf",    900, "normal"),
        ("Poppins-Bold.ttf",     700, "normal"),
        ("Poppins-SemiBold.ttf", 600, "normal"),
        ("Poppins-Medium.ttf",   500, "normal"),
        ("Poppins-Regular.ttf",  400, "normal"),
    ]
    css = ""
    for fname, weight, style in variants:
        fpath = FONTS_DIR / fname
        if fpath.exists():
            uri = fpath.as_uri()
            css += f"""@font-face {{
  font-family: 'Poppins';
  src: url('{uri}') format('truetype');
  font-weight: {weight};
  font-style: {style};
}}\n"""
    return css


def _lottie_player_script() -> str:
    """Script lottie-player local ou CDN fallback."""
    local = Path(__file__).parent.parent / "assets" / "js" / "lottie-player.js"
    if local.exists():
        return f'<script src="{local.as_uri()}"></script>'
    return '<script src="https://unpkg.com/@lottiefiles/lottie-player@1.5.7/dist/lottie-player.js"></script>'


def _build_lottie_injection(lottie_url: str) -> tuple[str, str]:
    """Retourne (src_attr, script_inline) pour charger Lottie sans erreur CORS."""
    src_attr = f'src="{lottie_url}"'
    inline_script = ""

    if lottie_url and lottie_url.startswith("file://"):
        try:
            import urllib.request
            fpath = urllib.request.url2pathname(lottie_url[7:])
            fpath = Path(fpath)

            if not fpath.exists():
                logging.warning(f"[LOTTIE] File not found: {fpath}")
                return src_attr, inline_script

            with open(fpath, "r", encoding="utf-8") as f:
                lottie_data = f.read()

            src_attr = ""
            # Attendre que le custom element soit ENREGISTRÉ avant d'appeler .load()
            # customElements.whenDefined est bien plus fiable qu'un setTimeout fixe.
            inline_script = (
                f"customElements.whenDefined('lottie-player').then(function(){{"
                f"var el=document.getElementById('lottie');"
                f"if(el&&typeof el.load==='function'){{el.load({lottie_data});}}"
                f"else{{setTimeout(function(){{document.getElementById('lottie').load({lottie_data});}},400);}}"
                f"}});"
            )
            logging.info(f"[LOTTIE] Injected locally: {fpath.name}")
        except Exception as e:
            logging.error(f"[LOTTIE] Injection failed: {e} — fallback to src")

    return src_attr, inline_script


def _webm_to_mp4(webm: Path, mp4: Path, audio_path: str = None) -> bool:
    """Convertit webm -> mp4, avec audio mux optionnel."""
    ffmpeg = _get_ffmpeg()
    if audio_path and Path(audio_path).exists():
        cmd = [
            ffmpeg, "-y",
            "-i", str(webm),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(mp4)
        ]
    else:
        cmd = [
            ffmpeg, "-y", "-i", str(webm),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(mp4)
        ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and mp4.exists()


def _record(html: str, duration: float, output: str, audio_path: str = None,
            lottie_url: str = "") -> bool:
    """
    Enregistre une page HTML en video via Playwright, puis mux l'audio.
    Si lottie_url fourni : attend que l'animation soit chargée avant de démarrer.
    """
    # Exécuter dans un thread séparé pour éviter les conflits asyncio
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_record_sync, html, duration, output, audio_path, lottie_url)
        return future.result()


def _record_sync(html: str, duration: float, output: str, audio_path: str = None,
                 lottie_url: str = "") -> bool:
    """Version synchrone de _record pour exécutée dans un thread."""
    from playwright.sync_api import sync_playwright

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    html_file = out.parent / f"_slide_{out.stem}.html"
    html_file.write_text(html, encoding="utf-8")

    video_dir = out.parent / f"_pw_{out.stem}"
    video_dir.mkdir(exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-web-security",
                      "--allow-file-access-from-files",
                      "--autoplay-policy=no-user-gesture-required"]
            )
            ctx = browser.new_context(
                viewport={"width": W, "height": H},
                record_video_dir=str(video_dir),
                record_video_size={"width": W, "height": H},
            )
            page = ctx.new_page()
            # Utiliser file:// avec chemin Windows absolu au lieu de .as_uri()
            file_path = html_file.absolute().as_posix()
            page.goto(f"file:///{file_path}", wait_until="load")

            # Attendre que le shadow root de lottie-player soit créé (= élément initialisé)
            if lottie_url:
                try:
                    page.wait_for_function(
                        "() => { const el = document.querySelector('#lottie'); "
                        "return el && el.shadowRoot !== null; }",
                        timeout=3000
                    )
                    page.wait_for_timeout(400)  # laisser la 1ère frame s'afficher
                except Exception:
                    page.wait_for_timeout(800)  # fallback : attendre 800ms

            # Enregistrer la durée + 600ms de buffer pour le flush codec Playwright
            page.wait_for_timeout(int(duration * 1000) + 600)
            ctx.close()
            browser.close()
    except Exception as e:
        logging.error(f"[SLIDE] Playwright: {e}")
        return False

    webms = list(video_dir.glob("*.webm"))
    if not webms:
        logging.error(f"[SLIDE] Pas de webm genere pour {out.stem}")
        return False

    webm = max(webms, key=lambda f: f.stat().st_mtime)
    ok = _webm_to_mp4(webm, out, audio_path)
    shutil.rmtree(video_dir, ignore_errors=True)
    html_file.unlink(missing_ok=True)
    return ok


def _preview_jpeg(html: str, output_jpeg: str) -> bool:
    """Capture un screenshot JPEG du slide (aperçu rapide, sans enregistrement vidéo)."""
    from playwright.sync_api import sync_playwright
    out = Path(output_jpeg)
    out.parent.mkdir(parents=True, exist_ok=True)
    html_file = out.parent / f"_prev_{out.stem}.html"
    html_file.write_text(html, encoding="utf-8")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-web-security",
                      "--allow-file-access-from-files"]
            )
            page = browser.new_page(viewport={"width": W, "height": H})
            file_path = html_file.absolute().as_posix()
            page.goto(f"file:///{file_path}", wait_until="load")
            page.wait_for_timeout(1200)  # laisser les animations GSAP démarrer
            page.screenshot(path=str(out), type="jpeg", quality=85)
            browser.close()
        html_file.unlink(missing_ok=True)
        return out.exists()
    except Exception as e:
        logging.error(f"[SLIDE] Preview JPEG: {e}")
        html_file.unlink(missing_ok=True)
        return False


# ── Templates par type ──────────────────────────────────────────────────────
# Principe commun à tous les templates :
#   • La lottie est position:absolute depuis LOTTIE_TOP, centrée horizontalement.
#   • La zone texte est position:absolute depuis TEXT_TOP avec overflow:hidden.
#     → Le premier élément texte apparaît toujours à la même hauteur (TEXT_TOP).
#     → Le texte ne peut pas dépasser le bas de l'écran (bottom = TEXT_MARGIN_BOTTOM).

def render_hook(title: str, subtitle: str, output: str, duration: float,
                lottie_url: str = "", audio_path: str = None,
                preview_path: str = None) -> bool:
    """Hook : Lottie en haut (absolue), titre + sous-titre dans zone fixe."""
    font_face     = _font_face_css()
    lottie_script = _lottie_player_script() if lottie_url else ""
    src_attr, inline_script = _build_lottie_injection(lottie_url) if lottie_url else ("", "")

    lottie_w    = 700
    lottie_left = (W - lottie_w) // 2   # 190px — centré horizontalement
    lottie_block = (
        f'<lottie-player id="lottie" {src_attr} background="transparent" '
        f'speed="1" loop autoplay style="position:absolute;top:{LOTTIE_TOP}px;left:{lottie_left}px;'
        f'width:{lottie_w}px;height:{lottie_w}px;opacity:0;transform:scale(0.7);"></lottie-player>\n'
        f'<script>{inline_script}</script>'
        if lottie_url else ''
    )

    html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
{lottie_script}
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
{font_face}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:1080px; height:1920px; overflow:hidden; background:#ffffff;
  font-family:'Poppins','Segoe UI',Arial,sans-serif; position:relative; }}
.wrap {{ position:absolute; inset:0; }}
.text-zone {{ position:absolute; top:{TEXT_TOP}px; left:90px; right:90px;
  bottom:{TEXT_BOTTOM}px; overflow:hidden;
  display:flex; flex-direction:column; align-items:center; text-align:center; }}
.accent-bar {{ width:0; height:6px; border-radius:3px; background:#d4af37; margin-bottom:36px; }}
.title {{ color:#111; font-size:104px; font-weight:900; line-height:1.1;
  letter-spacing:-2px; opacity:0; transform:translateY(50px); }}
.subtitle {{ color:#444; font-size:52px; font-weight:500; line-height:1.35;
  margin-top:28px; opacity:0; transform:translateY(30px); }}
.brand {{ position:absolute; top:72px; right:80px; font-size:24px; font-weight:700;
  letter-spacing:3px; text-transform:uppercase; color:#d4af37; opacity:0; }}
</style></head><body>
<div class="wrap">
  {lottie_block}
  <div class="text-zone">
    <div class="accent-bar" id="bar"></div>
    <div class="title" id="title">{title}</div>
    <div class="subtitle" id="sub">{subtitle}</div>
  </div>
</div>
<div class="brand" id="brand">IncidenX</div>
<script>
const tl = gsap.timeline();
{'gsap.to("#lottie", { opacity:1, scale:1, duration:0.7, ease:"back.out(1.4)", delay:0.1 });' if lottie_url else ''}
tl.to('#bar',   {{ width:'120px', duration:0.5, ease:'power2.out', delay:0.3 }})
  .to('#title', {{ opacity:1, y:0, duration:0.7, ease:'back.out(1.5)' }}, '-=0.1')
  .to('#sub',   {{ opacity:1, y:0, duration:0.6, ease:'power2.out' }}, '-=0.2')
  .to('#brand', {{ opacity:1, duration:0.4 }}, '-=0.2');
</script></body></html>"""

    if preview_path:
        _preview_jpeg(html, preview_path)
    return _record(html, duration, output, audio_path, lottie_url)


def render_tip(number: int, title: str, subtitle: str, output: str, duration: float,
               lottie_url: str = "", audio_path: str = None, layout: str = "top",
               preview_path: str = None) -> bool:
    font_face     = _font_face_css()
    lottie_script = _lottie_player_script() if lottie_url else ""
    src_attr, inline_script = _build_lottie_injection(lottie_url) if lottie_url else ("", "")
    LOTTIE_SIZE   = 660
    lottie_left   = (W - LOTTIE_SIZE) // 2   # 210px — centré horizontalement

    if layout == "top_right":
        # Lottie absolue en haut à droite, texte ancré en bas avec hauteur max
        lottie_block = (
            f'<lottie-player id="lottie" {src_attr} background="transparent" '
            f'speed="1" loop autoplay style="position:absolute;top:{LOTTIE_TOP}px;right:60px;'
            f'width:{LOTTIE_SIZE}px;height:{LOTTIE_SIZE}px;opacity:0;transform:scale(0.7);"></lottie-player>\n'
            f'<script>{inline_script}</script>'
            if lottie_url else ""
        )
        text_block = f"""
  <div style="position:absolute; top:{TEXT_TOP}px; left:90px; right:90px;
    bottom:{TEXT_BOTTOM}px; overflow:hidden; text-align:left;">
    <div class="number" id="num">{number}</div>
    <div class="accent-bar" id="bar"></div>
    <div class="title" id="title">{title}</div>
    <div class="subtitle" id="sub">{subtitle}</div>
  </div>"""

    elif layout == "top_left":
        # Lottie absolue en haut à gauche, texte ancré en bas avec hauteur max
        lottie_block = (
            f'<lottie-player id="lottie" {src_attr} background="transparent" '
            f'speed="1" loop autoplay style="position:absolute;top:{LOTTIE_TOP}px;left:60px;'
            f'width:{LOTTIE_SIZE}px;height:{LOTTIE_SIZE}px;opacity:0;transform:scale(0.7);"></lottie-player>\n'
            f'<script>{inline_script}</script>'
            if lottie_url else ""
        )
        text_block = f"""
  <div style="position:absolute; top:{TEXT_TOP}px; left:90px; right:90px;
    bottom:{TEXT_BOTTOM}px; overflow:hidden; text-align:right;">
    <div class="number" id="num" style="text-align:right;">{number}</div>
    <div class="accent-bar" id="bar" style="margin-left:auto;"></div>
    <div class="title" id="title">{title}</div>
    <div class="subtitle" id="sub">{subtitle}</div>
  </div>"""

    elif layout == "bottom":
        # Texte en haut, lottie absolue en bas
        lottie_block = (
            f'<lottie-player id="lottie" {src_attr} background="transparent" '
            f'speed="1" loop autoplay style="position:absolute;bottom:{LOTTIE_TOP}px;left:{lottie_left}px;'
            f'width:{LOTTIE_SIZE}px;height:{LOTTIE_SIZE}px;opacity:0;transform:scale(0.7);"></lottie-player>\n'
            f'<script>{inline_script}</script>'
            if lottie_url else ""
        )
        text_block = f"""
  <div style="position:absolute; top:200px; left:90px; right:90px;
    bottom:{TEXT_BOTTOM + 700}px; overflow:hidden; display:flex; flex-direction:column; align-items:flex-start;">
    <div class="number" id="num">{number}</div>
    <div class="accent-bar" id="bar"></div>
    <div class="title" id="title">{title}</div>
    <div class="subtitle" id="sub">{subtitle}</div>
  </div>"""

    else:  # "top" — layout par défaut
        # Lottie absolue en haut au centre.
        # Numéro watermark positionné absolument entre lottie et zone texte.
        # Zone texte (barre + titre + sous-titre) ancrée à TEXT_TOP.
        lottie_block = (
            f'<lottie-player id="lottie" {src_attr} background="transparent" '
            f'speed="1" loop autoplay style="position:absolute;top:{LOTTIE_TOP}px;left:{lottie_left}px;'
            f'width:{LOTTIE_SIZE}px;height:{LOTTIE_SIZE}px;opacity:0;transform:scale(0.7);"></lottie-player>\n'
            f'<script>{inline_script}</script>'
            if lottie_url else ""
        )
        text_block = f"""
  {lottie_block}
  <div class="number" id="num" style="position:absolute;top:{TIP_NUM_TOP}px;left:90px;">{number}</div>
  <div style="position:absolute; top:{TEXT_TOP}px; left:90px; right:90px;
    bottom:{TEXT_BOTTOM}px; overflow:hidden; display:flex; flex-direction:column; align-items:flex-start;">
    <div class="accent-bar" id="bar"></div>
    <div class="title" id="title">{title}</div>
    <div class="subtitle" id="sub">{subtitle}</div>
  </div>"""
        # lottie_block déjà inséré dans text_block ci-dessus → ne pas le redoubler
        lottie_block = ""

    html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
{lottie_script}
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
{font_face}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:1080px; height:1920px; overflow:hidden; background:#ffffff;
  font-family:'Poppins','Segoe UI',Arial,sans-serif; position:relative; }}
.wrap {{ position:absolute; inset:0; }}
.number {{ font-size:220px; font-weight:900; line-height:0.85; color:#d4af3760;
  opacity:0; transform:translateX(-40px); user-select:none; }}
.accent-bar {{ width:0; height:6px; border-radius:3px; background:#d4af37;
  margin:20px 0 28px 0; }}
.title {{ color:#111; font-size:88px; font-weight:900; line-height:1.1;
  letter-spacing:-2px; opacity:0; transform:translateY(40px); text-align:left; width:100%; }}
.subtitle {{ color:#444; font-size:48px; font-weight:500; line-height:1.35;
  margin-top:24px; opacity:0; transform:translateY(25px); text-align:left; width:100%; }}
.brand {{ position:absolute; top:72px; right:80px; font-size:24px; font-weight:700;
  letter-spacing:3px; text-transform:uppercase; color:#d4af37; opacity:0; }}
</style></head><body>
<div class="wrap">
  {lottie_block}
  {text_block}
</div>
<div class="brand" id="brand">IncidenX</div>
<script>
{'gsap.to("#lottie", { opacity:1, scale:1, duration:0.7, ease:"back.out(1.4)", delay:0.1 });' if lottie_url else ''}
const tl = gsap.timeline();
tl.to('#num',   {{ opacity:1, x:0, duration:0.5, ease:'power2.out', delay:0.2 }})
  .to('#bar',   {{ width:'100px', duration:0.4, ease:'power2.out' }}, '-=0.2')
  .to('#title', {{ opacity:1, y:0, duration:0.65, ease:'back.out(1.4)' }}, '-=0.2')
  .to('#sub',   {{ opacity:1, y:0, duration:0.55, ease:'power2.out' }}, '-=0.2')
  .to('#brand', {{ opacity:1, duration:0.4 }}, '-=0.2');
</script></body></html>"""

    if preview_path:
        _preview_jpeg(html, preview_path)
    return _record(html, duration, output, audio_path, lottie_url)


def render_proof(title: str, subtitle: str, output: str, duration: float,
                 lottie_url: str = "", audio_path: str = None,
                 preview_path: str = None) -> bool:
    """Proof : lottie en haut (absolue), zone texte fixe avec quote + titre + sous-titre."""
    font_face     = _font_face_css()
    lottie_script = _lottie_player_script() if lottie_url else ""
    src_attr, inline_script = _build_lottie_injection(lottie_url) if lottie_url else ("", "")

    lottie_w    = 680
    lottie_left = (W - lottie_w) // 2   # 200px
    lottie_block = (
        f'<lottie-player id="lottie" {src_attr} background="transparent" '
        f'speed="1" autoplay style="position:absolute;top:{LOTTIE_TOP}px;left:{lottie_left}px;'
        f'width:{lottie_w}px;height:{lottie_w}px;opacity:0;"></lottie-player>\n'
        f'<script>{inline_script}</script>'
        if lottie_url else ''
    )

    html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
{lottie_script}
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
{font_face}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:1080px; height:1920px; overflow:hidden; background:#ffffff;
  font-family:'Poppins','Segoe UI',Arial,sans-serif; position:relative; }}
.wrap {{ position:absolute; inset:0; }}
.text-zone {{ position:absolute; top:{TEXT_TOP}px; left:90px; right:90px;
  bottom:{TEXT_BOTTOM}px; overflow:hidden;
  display:flex; flex-direction:column; align-items:center; text-align:center; }}
.quote {{ font-size:240px; line-height:0.7; color:#d4af3722;
  font-family:Georgia,serif; opacity:0; }}
.title {{ color:#111; font-size:92px; font-weight:900; line-height:1.1;
  opacity:0; transform:translateY(40px); margin-top:10px; }}
.subtitle {{ color:#444; font-size:50px; font-weight:500; line-height:1.35;
  margin-top:28px; opacity:0; transform:translateY(25px); }}
.brand {{ position:absolute; top:72px; right:80px; font-size:24px; font-weight:700;
  letter-spacing:3px; text-transform:uppercase; color:#d4af37; opacity:0; }}
</style></head><body>
<div class="wrap">
  {lottie_block}
  <div class="text-zone">
    <div class="quote" id="q">"</div>
    <div class="title" id="title">{title}</div>
    <div class="subtitle" id="sub">{subtitle}</div>
  </div>
</div>
<div class="brand" id="brand">IncidenX</div>
<script>
{'gsap.to("#lottie", { opacity:1, duration:0.6, delay:0.1 });' if lottie_url else ''}
const tl = gsap.timeline();
tl.to('#q',     {{ opacity:1, duration:0.5, delay:0.2 }})
  .to('#title', {{ opacity:1, y:0, duration:0.7, ease:'back.out(1.4)' }}, '-=0.1')
  .to('#sub',   {{ opacity:1, y:0, duration:0.55, ease:'power2.out' }}, '-=0.2')
  .to('#brand', {{ opacity:1, duration:0.4 }}, '-=0.2');
</script></body></html>"""

    if preview_path:
        _preview_jpeg(html, preview_path)
    return _record(html, duration, output, audio_path, lottie_url)


def render_cta(title: str, subtitle: str, output: str, duration: float,
               lottie_url: str = "", audio_path: str = None,
               preview_path: str = None) -> bool:
    """CTA : fond or, lottie pulsante en haut (absolue), titre + sous-titre dans zone fixe."""
    font_face     = _font_face_css()
    lottie_script = _lottie_player_script() if lottie_url else ""
    src_attr, inline_script = _build_lottie_injection(lottie_url) if lottie_url else ("", "")

    lottie_w    = 600
    lottie_left = (W - lottie_w) // 2   # 240px
    lottie_block = (
        f'<lottie-player id="lottie" {src_attr} background="transparent" '
        f'speed="1" loop autoplay style="position:absolute;top:{LOTTIE_TOP}px;left:{lottie_left}px;'
        f'width:{lottie_w}px;height:{lottie_w}px;opacity:0;"></lottie-player>\n'
        f'<script>{inline_script}</script>'
        if lottie_url else '<div class="arrow" id="arr">👇</div>'
    )

    html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
{lottie_script}
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<style>
{font_face}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:1080px; height:1920px; overflow:hidden;
  background:linear-gradient(145deg,#d4af37,#f5d97a,#d4af37);
  font-family:'Poppins','Segoe UI',Arial,sans-serif; position:relative; }}
.wrap {{ position:absolute; inset:0; }}
.text-zone {{ position:absolute; top:{TEXT_TOP}px; left:90px; right:90px;
  bottom:{TEXT_BOTTOM}px; overflow:hidden;
  display:flex; flex-direction:column; align-items:center; text-align:center; }}
.arrow {{ font-size:140px; opacity:0; margin-bottom:20px; }}
.title {{ color:#111; font-size:100px; font-weight:900; line-height:1.1;
  letter-spacing:-2px; opacity:0; transform:translateY(40px); }}
.subtitle {{ color:#111c; font-size:52px; font-weight:500; line-height:1.35;
  margin-top:28px; opacity:0; transform:translateY(25px); }}
.brand {{ position:absolute; top:72px; right:80px; font-size:24px; font-weight:700;
  letter-spacing:3px; text-transform:uppercase; color:#111; opacity:0; }}
</style></head><body>
<div class="wrap">
  {lottie_block}
  <div class="text-zone">
    <div class="title" id="title">{title}</div>
    <div class="subtitle" id="sub">{subtitle}</div>
  </div>
</div>
<div class="brand" id="brand">IncidenX</div>
<script>
{'gsap.to("#lottie", { opacity:1, scale:1, duration:0.6, ease:"back.out(1.4)", delay:0.1 });' if lottie_url else 'gsap.to("#arr", { opacity:1, duration:0.5, delay:0.1 }); gsap.to("#arr", { y:20, duration:0.7, ease:"power1.inOut", repeat:-1, yoyo:true, delay:1 });'}
const tl = gsap.timeline();
tl.to('#title', {{ opacity:1, y:0, duration:0.7, ease:'back.out(1.4)', delay:0.3 }})
  .to('#sub',   {{ opacity:1, y:0, duration:0.55, ease:'power2.out' }}, '-=0.2')
  .to('#brand', {{ opacity:1, duration:0.4 }}, '-=0.2');
</script></body></html>"""

    if preview_path:
        _preview_jpeg(html, preview_path)
    return _record(html, duration, output, audio_path, lottie_url)


def render_slide(scene: dict, output: str, audio_path: str = None,
                 preview_path: str = None) -> bool:
    """
    Point d'entree unique.
    audio_path   : fichier TTS du slide -> mux directement dans le MP4.
    preview_path : si fourni, capture un JPEG avant le rendu video.
    """
    import sys
    sys.path.append(str(Path(__file__).parent))
    from lottie_library import get_lottie_for_scene

    stype    = scene.get("type", "tip")
    title    = scene.get("title", "")
    subtitle = scene.get("subtitle", "")
    duration = float(scene.get("duration", 3.5))
    number   = int(scene.get("number", 1))

    lottie_url = get_lottie_for_scene(scene) or ""

    TIP_LAYOUTS = ["top", "top_right", "top_left"]

    if stype == "hook":
        return render_hook(title, subtitle, output, duration, lottie_url, audio_path, preview_path)
    elif stype == "tip":
        layout = TIP_LAYOUTS[(number - 1) % len(TIP_LAYOUTS)]
        return render_tip(number, title, subtitle, output, duration, lottie_url,
                          audio_path, layout=layout, preview_path=preview_path)
    elif stype == "proof":
        return render_proof(title, subtitle, output, duration, lottie_url, audio_path, preview_path)
    elif stype == "cta":
        return render_cta(title, subtitle, output, duration, lottie_url, audio_path, preview_path)
    else:
        return render_hook(title, subtitle, output, duration, lottie_url, audio_path, preview_path)


if __name__ == "__main__":
    import os
    os.makedirs("d:/Content_Machine/machines/facebook-machine/temp", exist_ok=True)

    scenes = [
        {"type": "hook",  "title": "3 astuces pour devenir independant",
         "subtitle": "Applique-les et ta vie change en 90 jours.",
         "lottie_keyword": "freelance", "duration": 3.0},
        {"type": "tip",   "number": 1, "title": "Gere ton temps comme si tu mourais demain.",
         "subtitle": "La vie est courte. Chaque heure perdue ne revient jamais.",
         "lottie_keyword": "clock", "duration": 4.0},
        {"type": "cta",   "title": "Tu veux devenir independant ?",
         "subtitle": "Commente LIBRE et je t'envoie mon guide gratuit.",
         "lottie_keyword": "cta", "duration": 4.0},
    ]

    base = "d:/Content_Machine/machines/facebook-machine/temp"
    for i, scene in enumerate(scenes):
        out  = f"{base}/slide_{i:02d}_{scene['type']}.mp4"
        prev = f"{base}/preview_{i:02d}_{scene['type']}.jpg"
        ok = render_slide(scene, out, preview_path=prev)
        print(f"Slide {i+1} ({scene['type']}) : {'OK' if ok else 'FAIL'}")
