"""Shared figure style: small static PNGs for the Markdown reports.

Colours follow the validated reference palette of the team's data-visualisation method:
three categorical slots (blue, orange, aqua; checked for colour-vision deficiency with
the palette validator, all pairs), status colours only for status, ink colours for text,
hairline solid grids, 2 px lines, markers with a surface ring, a single y-axis per chart.
Every figure is paired with a table in the report, so no value depends on colour alone.

PNG files carry no timestamp or software metadata, so identical inputs give identical
bytes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
DPI = 110


def _style() -> dict[str, Any]:
    return {
        "font.family": "sans-serif",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.labelsize": 9,
        "axes.labelcolor": INK_SECONDARY,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.facecolor": SURFACE,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_SECONDARY,
        "ytick.labelcolor": INK_SECONDARY,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.frameon": False,
        "legend.fontsize": 8,
        "legend.labelcolor": INK_SECONDARY,
        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "figure.facecolor": SURFACE,
        "text.color": INK,
        "svg.hashsalt": "yield-guardian",
    }


def figure(
    width: float = 6.4, height: float = 3.2, ncols: int = 1, nrows: int = 1
) -> tuple[Figure, Any]:
    """A new figure with the report style applied (the style is set process-wide)."""
    mpl.rcParams.update(cast(Any, _style()))
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height), layout="constrained")
    return fig, axes


def apply_style(ax: Axes) -> None:
    """Re-apply the style to an axes created outside ``figure``."""
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)


def save(fig: Figure, path: Path) -> Path:
    """Write a PNG without metadata and close the figure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)
    return path
