# sfx_generator.py -- Génère les SFX de montage synthétiques en WAV local
# Utilise numpy uniquement — aucune dépendance externe, aucun téléchargement
#
# Usage : python cinema/sfx_generator.py

import numpy as np
import wave
from pathlib import Path

SFX_DIR = Path(__file__).parent.parent / "assets" / "sfx"
SR = 44100  # sample rate


def _save_wav(samples: np.ndarray, path: Path, sr: int = SR):
    """Sauvegarde un tableau numpy en fichier WAV mono 16-bit."""
    samples = np.clip(samples, -1.0, 1.0)
    data = (samples * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())


def _envelope(n: int, attack: float = 0.05, decay: float = 0.1,
              sustain: float = 0.7, release: float = 0.3) -> np.ndarray:
    """ADSR envelope normalisée."""
    a = int(n * attack)
    d = int(n * decay)
    r = int(n * release)
    s = n - a - d - r
    env = np.concatenate([
        np.linspace(0, 1, a),
        np.linspace(1, sustain, d),
        np.full(max(s, 0), sustain),
        np.linspace(sustain, 0, r),
    ])
    return env[:n]


def gen_whoosh_in(duration: float = 0.4) -> np.ndarray:
    """Whoosh ascendant — entrée d'élément."""
    n = int(SR * duration)
    freq = np.linspace(200, 1800, n)  # sweep montant
    phase = np.cumsum(freq / SR * 2 * np.pi)
    noise = np.random.randn(n) * 0.3
    tone = np.sin(phase) * 0.5
    sig = (tone + noise) * _envelope(n, 0.02, 0.1, 0.6, 0.28)
    # Filtre passe-haut simple (différence)
    sig = np.diff(sig, prepend=sig[0]) * 8
    return sig * np.linspace(0.3, 1.0, n)


def gen_whoosh_out(duration: float = 0.35) -> np.ndarray:
    """Whoosh descendant — sortie d'élément."""
    n = int(SR * duration)
    freq = np.linspace(1800, 150, n)  # sweep descendant
    phase = np.cumsum(freq / SR * 2 * np.pi)
    noise = np.random.randn(n) * 0.25
    tone = np.sin(phase) * 0.5
    sig = (tone + noise) * _envelope(n, 0.01, 0.05, 0.5, 0.44)
    sig = np.diff(sig, prepend=sig[0]) * 7
    return sig * np.linspace(1.0, 0.2, n)


def gen_pop(duration: float = 0.15) -> np.ndarray:
    """Pop/ding — apparition d'un élément clé."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n)
    # Fondamentale + harmoniques
    f0 = 880
    sig = (np.sin(2 * np.pi * f0 * t) * 0.6 +
           np.sin(2 * np.pi * f0 * 2 * t) * 0.25 +
           np.sin(2 * np.pi * f0 * 3 * t) * 0.1)
    env = np.exp(-t * 18)
    return sig * env * 0.9


def gen_ding(duration: float = 0.5) -> np.ndarray:
    """Ding métallique clair — highlight chiffre/stat."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n)
    f0 = 1320
    sig = (np.sin(2 * np.pi * f0 * t) * 0.5 +
           np.sin(2 * np.pi * f0 * 2.76 * t) * 0.2 +  # inharmonique = son métal
           np.sin(2 * np.pi * f0 * 0.5 * t) * 0.15)
    env = np.exp(-t * 7)
    return sig * env


def gen_impact(duration: float = 0.3) -> np.ndarray:
    """Impact/boom — transition entre slides."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n)
    # Basse percussive
    bass = np.sin(2 * np.pi * np.linspace(80, 40, n) * t) * 0.7
    # Noise burst
    noise = np.random.randn(n) * 0.4
    click = np.zeros(n)
    click[:50] = np.linspace(1, 0, 50)  # click initial
    sig = bass + noise * np.exp(-t * 12) + click
    env = np.exp(-t * 6)
    return sig * env


def gen_swoosh(duration: float = 0.45) -> np.ndarray:
    """Swoosh latéral — mouvement de slide."""
    n = int(SR * duration)
    noise = np.random.randn(n)
    # Filtre temporel par multiplication avec une fréquence modulée
    mod = np.sin(np.linspace(0, np.pi * 3, n)) * 0.5 + 0.5
    env = _envelope(n, 0.03, 0.15, 0.4, 0.42)
    sig = noise * mod * env
    # Différenciation pour effet "air"
    sig = np.diff(sig, prepend=sig[0]) * 5
    return sig * 0.8


def gen_notification(duration: float = 0.6) -> np.ndarray:
    """Notification douce — CTA slide."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n)
    # Deux notes successives (quinte)
    n1 = int(n * 0.4)
    t1 = t[:n1]
    t2 = t[n1:]
    tone1 = np.sin(2 * np.pi * 880 * t1) * np.exp(-t1 * 10)
    tone2 = np.sin(2 * np.pi * 1320 * t2) * np.exp(-t2 * 8)
    return np.concatenate([tone1, tone2]) * 0.7


def gen_success(duration: float = 0.8) -> np.ndarray:
    """Fanfare courte — slide proof/trophy."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n)
    # Arpège ascendant Do-Mi-Sol
    freqs = [523, 659, 784]
    seg = n // 3
    sig = np.zeros(n)
    for i, f in enumerate(freqs):
        s, e = i * seg, min((i + 1) * seg + int(SR * 0.15), n)
        ts = t[s:e]
        note = np.sin(2 * np.pi * f * ts) * np.exp(-ts * 5)
        sig[s:s + len(note)] += note * 0.5
    return sig


def gen_transition(duration: float = 0.25) -> np.ndarray:
    """Transition rapide — entre deux sections."""
    n = int(SR * duration)
    whoosh = gen_whoosh_in(duration * 0.6)
    pop    = gen_pop(duration * 0.4)
    # Aligner sur n
    whoosh_pad = np.zeros(n)
    whoosh_pad[:min(len(whoosh), n)] = whoosh[:n]
    pop_offset = int(n * 0.5)
    pop_pad = np.zeros(n)
    pop_end = min(pop_offset + len(pop), n)
    pop_pad[pop_offset:pop_end] = pop[:pop_end - pop_offset]
    return (whoosh_pad * 0.6 + pop_pad * 0.5)


def gen_boom_impact(duration: float = 0.5) -> np.ndarray:
    """Boom grave — slide hook très percutant."""
    n = int(SR * duration)
    t = np.linspace(0, duration, n)
    sub = np.sin(2 * np.pi * 55 * t) * 0.8        # sub-bass
    mid = np.sin(2 * np.pi * 110 * t) * 0.4       # corps
    noise = np.random.randn(n) * 0.3
    env = np.exp(-t * 5)
    punch = np.zeros(n)
    punch[:int(SR * 0.02)] = 1.0  # punch initial
    sig = (sub + mid + noise) * env + punch
    return np.clip(sig, -1, 1)


# ---------------------------------------------------------------------------
# Génération du pack complet
# ---------------------------------------------------------------------------

SFX_GENERATORS = {
    "whoosh_in.wav":    gen_whoosh_in,
    "whoosh_out.wav":   gen_whoosh_out,
    "pop.wav":          gen_pop,
    "ding.wav":         gen_ding,
    "impact.wav":       gen_impact,
    "swoosh.wav":       gen_swoosh,
    "notification.wav": gen_notification,
    "success.wav":      gen_success,
    "transition.wav":   gen_transition,
    "boom.wav":         gen_boom_impact,
}


def generate_all(force: bool = False):
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n[SFX] Génération de {len(SFX_GENERATORS)} effets sonores...")
    print(f"      Dossier : {SFX_DIR}\n")
    for name, fn in SFX_GENERATORS.items():
        out = SFX_DIR / name
        if out.exists() and not force:
            print(f"  SKIP {name}")
            continue
        samples = fn()
        _save_wav(samples, out)
        print(f"  OK   {name}  ({out.stat().st_size // 1024}KB, {len(samples)/SR:.2f}s)")
    print(f"\n[SFX] Terminé — {len(SFX_GENERATORS)} fichiers dans {SFX_DIR}\n")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    generate_all(force=args.force)
