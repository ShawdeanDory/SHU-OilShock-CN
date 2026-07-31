"""Paper-oriented Matplotlib style helpers for the oil-shock figures."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
from cycler import cycler


INK = "#232323"
MUTED = "#606060"
GRID = "#d9d4ca"
SPINE = "#4a4a4a"

PALETTE = {
    "ink": INK,
    "muted": MUTED,
    "grid": GRID,
    "blue": "#355c7d",
    "blue_light": "#9fb4c9",
    "gold": "#b98b3d",
    "gold_light": "#d8c49a",
    "olive": "#6f7f4f",
    "olive_light": "#b8c1a3",
    "rose": "#a65d6a",
    "rose_light": "#d4a7af",
    "slate": "#6f7582",
    "sand": "#c9b99a",
}

SERIES_COLORS = [
    PALETTE["blue"],
    PALETTE["gold"],
    PALETTE["olive"],
    PALETTE["rose"],
    PALETTE["slate"],
]


def apply_paper_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.edgecolor": "white",
            "font.family": ["Times New Roman", "SimSun", "FangSong", "DejaVu Serif"],
            "font.serif": ["Times New Roman", "SimSun", "FangSong", "STIXGeneral", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "axes.unicode_minus": False,
            "text.color": INK,
            "axes.labelcolor": INK,
            "axes.edgecolor": SPINE,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.55,
            "grid.alpha": 0.75,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.major.width": 0.65,
            "ytick.major.width": 0.65,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "axes.labelsize": 10.5,
            "axes.titlesize": 13,
            "legend.fontsize": 9.2,
            "legend.frameon": False,
            "lines.linewidth": 1.65,
            "lines.markersize": 4.2,
            "patch.edgecolor": "white",
            "axes.prop_cycle": cycler(color=SERIES_COLORS),
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def style_axis(ax: plt.Axes, *, ylabel: str | None = None, xlabel: str | None = None) -> None:
    if ylabel:
        ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)
    ax.grid(True, axis="y")
    ax.grid(False, axis="x")
    ax.tick_params(length=3.2, width=0.65)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color(SPINE)
        ax.spines[side].set_linewidth(0.8)


def finish_figure(
    fig: plt.Figure,
    *,
    title: str,
    subtitle: str,
    source: str,
    rect: tuple[float, float, float, float] = (0.08, 0.11, 0.98, 0.86),
) -> None:
    fig.tight_layout(rect=rect)
    fig.text(rect[0], 0.965, title, ha="left", va="top", fontsize=14, fontweight="normal", color=INK)
    fig.text(rect[0], 0.927, subtitle, ha="left", va="top", fontsize=9.6, color=MUTED)
    fig.text(rect[0], 0.035, source, ha="left", va="bottom", fontsize=8.4, color=MUTED)


def save_figure(fig: plt.Figure, path_stem: Path, *, dpi: int = 300) -> None:
    fig.savefig(path_stem.with_suffix(".png"), dpi=dpi, bbox_inches="tight", pad_inches=0.08)
    fixed_time = datetime(2026, 7, 30, tzinfo=timezone.utc)
    pdf_metadata = {
        "Creator": "SHU-OilShock-CN",
        "Producer": "Matplotlib",
        "CreationDate": fixed_time,
        "ModDate": fixed_time,
    }
    fig.savefig(
        path_stem.with_suffix(".pdf"),
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=0.08,
        metadata=pdf_metadata,
    )
