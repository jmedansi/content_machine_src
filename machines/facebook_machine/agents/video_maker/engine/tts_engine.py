# tts_engine.py -- Microsoft Edge Neural TTS (gratuit, Python 3.14 compatible)
# Voix: fr-FR-DeniseNeural (femme) | fr-FR-HenriNeural (homme)
import asyncio
import logging
from pathlib import Path

DEFAULT_VOICE = "fr-FR-HenriNeural"
DEFAULT_RATE  = "+0%"
DEFAULT_PITCH = "+0Hz"


async def _synthesize(text: str, output_path: str, voice: str, rate: str, pitch: str):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def synthesize(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
) -> bool:
    """
    Genere un fichier audio MP3 depuis du texte via edge-tts.
    Returns True si OK.
    """
    try:
        # Utiliser une nouvelle event loop dans un thread pour éviter les conflits
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_run_synthesize_sync, text, output_path, voice, rate, pitch)
            return future.result()
    except Exception as e:
        logging.error(f"[TTS] Error: {e}")
        return False


def _run_synthesize_sync(text: str, output_path: str, voice: str, rate: str, pitch: str):
    """Exécute la synthèse dans une event loop isolée."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_synthesize(text, output_path, voice, rate, pitch))
        finally:
            loop.close()
    except Exception as e:
        logging.error(f"[TTS] Sync Error: {e}")
        return False
    
    p = Path(output_path)
    if p.exists() and p.stat().st_size > 1000:
        logging.info(f"[TTS] OK: {p.name} ({p.stat().st_size // 1024} KB)")
        return True
    logging.error(f"[TTS] File empty or missing: {output_path}")
    return False


def synthesize_segments(segments: list, output_dir: str, voice: str = DEFAULT_VOICE) -> list:
    """
    Genere un fichier audio par segment.
    segments = [{"text": "...", ...}, ...]
    Retourne la liste enrichie avec "audio_path" par segment.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for i, seg in enumerate(segments):
        text = seg.get("narration", seg.get("text", ""))
        if not text.strip():
            result.append({**seg, "audio_path": None})
            continue
        audio_file = str(out_dir / f"tts_{i:02d}.mp3")
        ok = synthesize(text, audio_file, voice=voice)
        result.append({**seg, "audio_path": audio_file if ok else None})
        print(f"[TTS] Segment {i+1}/{len(segments)}: {'OK' if ok else 'FAIL'}")
    return result


if __name__ == "__main__":
    ok = synthesize(
        "Bonjour. Voici comment tripler tes revenus en 30 jours.",
        "d:/Content_Machine/machines/facebook-machine/temp/test_tts.mp3"
    )
    print("TTS OK" if ok else "TTS FAIL")
