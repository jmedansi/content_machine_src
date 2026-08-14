# chart_renderer.py -- Graphiques animes via Matplotlib -> MP4
# Remplace Manim (incompatible Python 3.14)
# Supporte: bar chart race, line chart, pie chart, counter, stat reveal
import logging
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

W_PX, H_PX = 1080, 1920
DPI = 100
FPS = 30
FFMPEG_PATH = r"C:\ffmpeg\ffmpeg-8.1-essentials_build\bin\ffmpeg.exe"

GOLD   = "#d4af37"
WHITE  = "#f8fafc"
BG     = "#020617"
DARK   = "#0c1a3a"
ACCENT = "#38bdf8"


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


def _fig(bg=BG):
    fig = plt.figure(figsize=(W_PX / DPI, H_PX / DPI), dpi=DPI, facecolor=bg)
    ax = fig.add_subplot(111, facecolor=bg)
    ax.tick_params(colors=WHITE, labelsize=22)
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK)
    return fig, ax


def render_bar_chart_race(
    data: list,
    output_path: str,
    title: str = "",
    duration: float = 5.0,
    theme: dict = None,
) -> bool:
    """
    Bar chart race anime.
    data = [
      {"label": "Freelance", "start": 10, "end": 85},
      {"label": "Salarie",   "start": 20, "end": 40},
      ...
    ]
    """
    bg_color  = theme.get("bg", BG)       if theme else BG
    txt_color = theme.get("text", WHITE)  if theme else WHITE

    n_frames = int(duration * FPS)
    labels = [d["label"] for d in data]
    starts = np.array([d.get("start", 0) for d in data], dtype=float)
    ends   = np.array([d["end"] for d in data], dtype=float)

    fig, ax = _fig(bg=bg_color)
    colors = [GOLD, ACCENT, "#22c55e", "#f97316", "#a78bfa", "#f43f5e"]

    def update(frame):
        ax.clear()
        ax.set_facecolor(bg_color)
        t = frame / max(n_frames - 1, 1)
        # ease out cubic
        t_eased = 1 - (1 - t) ** 3
        values = starts + (ends - starts) * t_eased

        # Sort by value descending
        order = np.argsort(values)[::-1]
        sorted_labels = [labels[i] for i in order]
        sorted_values = values[order]
        bar_colors = [colors[i % len(colors)] for i in order]

        bars = ax.barh(
            sorted_labels, sorted_values,
            color=bar_colors, height=0.6,
            edgecolor="none"
        )

        # Value labels
        for bar, val in zip(bars, sorted_values):
            ax.text(
                val + max(ends) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:.0f}%", va="center", ha="left",
                color=txt_color, fontsize=24, fontweight="bold"
            )

        ax.set_xlim(0, max(ends) * 1.18)
        ax.set_facecolor(bg_color)
        ax.tick_params(colors=txt_color, labelsize=26)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.xaxis.set_visible(False)
        if title:
            ax.set_title(title, color=txt_color, fontsize=34, fontweight="bold", pad=30)
        fig.patch.set_facecolor(bg_color)

    ani = animation.FuncAnimation(fig, update, frames=n_frames, interval=1000 / FPS)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    writer = animation.FFMpegWriter(fps=FPS, codec="libx264",
                                    extra_args=["-pix_fmt", "yuv420p", "-crf", "18"])
    writer.ffmpeg_binary = _get_ffmpeg()

    try:
        ani.save(str(out), writer=writer, dpi=DPI)
        plt.close(fig)
        logging.info(f"[CHART] bar_race OK: {out.name}")
        print(f"[CHART] bar_race -> {out.name}")
        return True
    except Exception as e:
        plt.close(fig)
        logging.error(f"[CHART] bar_race error: {e}")
        print(f"[CHART] ERROR: {e}")
        return False


def render_line_chart(
    series: list,
    output_path: str,
    title: str = "",
    x_label: str = "",
    y_label: str = "",
    duration: float = 4.0,
) -> bool:
    """
    Courbe qui se trace progressivement.
    series = [
      {"label": "Revenus", "x": [1,2,3,4,5], "y": [10,25,40,60,90]},
    ]
    """
    n_frames = int(duration * FPS)
    colors = [GOLD, ACCENT, "#22c55e", "#f97316"]

    fig, ax = _fig()

    def update(frame):
        ax.clear()
        ax.set_facecolor(BG)
        t = frame / max(n_frames - 1, 1)
        t_eased = 1 - (1 - t) ** 2

        for i, s in enumerate(series):
            x = np.array(s["x"])
            y = np.array(s["y"])
            n_show = max(2, int(t_eased * len(x)))
            col = colors[i % len(colors)]
            ax.plot(x[:n_show], y[:n_show], color=col, linewidth=4,
                    label=s.get("label", ""), solid_capstyle="round")
            # Dot at tip
            if n_show > 0:
                ax.scatter([x[n_show - 1]], [y[n_show - 1]],
                           color=col, s=160, zorder=5)

        ax.set_facecolor(BG)
        ax.tick_params(colors=WHITE, labelsize=22)
        for spine in ax.spines.values():
            spine.set_edgecolor(DARK)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if title:
            ax.set_title(title, color=WHITE, fontsize=32, fontweight="bold", pad=24)
        if x_label:
            ax.set_xlabel(x_label, color=WHITE, fontsize=22)
        if y_label:
            ax.set_ylabel(y_label, color=WHITE, fontsize=22)
        if len(series) > 1:
            legend = ax.legend(facecolor=DARK, edgecolor=DARK, labelcolor=WHITE, fontsize=20)
        fig.patch.set_facecolor(BG)

    ani = animation.FuncAnimation(fig, update, frames=n_frames, interval=1000 / FPS)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = animation.FFMpegWriter(fps=FPS, codec="libx264",
                                    extra_args=["-pix_fmt", "yuv420p", "-crf", "18"])
    writer.ffmpeg_binary = _get_ffmpeg()
    try:
        ani.save(str(out), writer=writer, dpi=DPI)
        plt.close(fig)
        print(f"[CHART] line_chart -> {out.name}")
        return True
    except Exception as e:
        plt.close(fig)
        print(f"[CHART] ERROR: {e}")
        return False


def render_stat_counter(
    stats: list,
    output_path: str,
    duration: float = 3.5,
) -> bool:
    """
    Chiffres qui comptent jusqu'a la valeur cible. Effet tres impactant.
    stats = [
      {"label": "Clients gagnés", "value": 127, "suffix": "+"},
      {"label": "Revenus doublés", "value": 2,  "suffix": "x"},
    ]
    """
    n_frames = int(duration * FPS)

    fig = plt.figure(figsize=(W_PX / DPI, H_PX / DPI), dpi=DPI, facecolor=BG)
    ax = fig.add_subplot(111, facecolor=BG)
    ax.axis("off")

    n = len(stats)

    def update(frame):
        ax.clear()
        ax.set_facecolor(BG)
        ax.axis("off")
        t = frame / max(n_frames - 1, 1)
        t_eased = 1 - (1 - t) ** 3

        y_positions = np.linspace(0.75, 0.25, n)
        for i, stat in enumerate(stats):
            target = stat["value"]
            current = int(t_eased * target)
            suffix = stat.get("suffix", "")
            prefix = stat.get("prefix", "")
            label = stat.get("label", "")

            # Big number
            ax.text(0.5, y_positions[i] + 0.06, f"{prefix}{current}{suffix}",
                    transform=ax.transAxes, ha="center", va="center",
                    fontsize=120, fontweight="black", color=GOLD,
                    fontfamily="sans-serif")
            # Label
            ax.text(0.5, y_positions[i] - 0.06, label,
                    transform=ax.transAxes, ha="center", va="center",
                    fontsize=36, color=WHITE, fontfamily="sans-serif")
            # Divider
            if i < n - 1:
                mid_y = (y_positions[i] + y_positions[i + 1]) / 2
                ax.plot([0.1, 0.9], [mid_y, mid_y],
                        color=DARK, linewidth=2, transform=ax.transAxes,
                        clip_on=False)

        fig.patch.set_facecolor(BG)

    ani = animation.FuncAnimation(fig, update, frames=n_frames, interval=1000 / FPS)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = animation.FFMpegWriter(fps=FPS, codec="libx264",
                                    extra_args=["-pix_fmt", "yuv420p", "-crf", "18"])
    writer.ffmpeg_binary = _get_ffmpeg()
    try:
        ani.save(str(out), writer=writer, dpi=DPI)
        plt.close(fig)
        print(f"[CHART] stat_counter -> {out.name}")
        return True
    except Exception as e:
        plt.close(fig)
        print(f"[CHART] ERROR: {e}")
        return False


if __name__ == "__main__":
    import os
    os.makedirs("d:/Content_Machine/machines/facebook_machine/temp", exist_ok=True)

    print("Test 1: bar chart race...")
    render_bar_chart_race(
        data=[
            {"label": "Freelance", "start": 5,  "end": 85},
            {"label": "Salarie",   "start": 20, "end": 40},
            {"label": "Agence",    "start": 10, "end": 65},
            {"label": "Startup",   "start": 3,  "end": 72},
        ],
        title="Croissance des revenus (%)",
        output_path="d:/Content_Machine/machines/facebook_machine/temp/test_bar.mp4",
        duration=4.0,
    )

    print("Test 2: stat counter...")
    render_stat_counter(
        stats=[
            {"label": "Clients gagnés", "value": 127, "suffix": "+"},
            {"label": "Revenus x", "value": 3, "suffix": "x"},
        ],
        output_path="d:/Content_Machine/machines/facebook_machine/temp/test_stats.mp4",
        duration=3.5,
    )

    print("Test 3: line chart...")
    render_line_chart(
        series=[{"label": "Revenus", "x": list(range(1, 7)), "y": [10, 18, 35, 52, 74, 110]}],
        title="Progression mensuelle",
        output_path="d:/Content_Machine/machines/facebook_machine/temp/test_line.mp4",
        duration=4.0,
    )
