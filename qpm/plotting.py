"""Charts for slides (static PNG). Palette and mark specs follow the team's dataviz rules:
fixed categorical order, 2px lines, hairline solid grid, legend for >= 2 series, text in ink colours."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE_RAMP = {100: "#cde2fb", 150: "#b7d3f6", 200: "#9ec5f4", 250: "#86b6ef", 300: "#6da7ec"}
INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781",
       "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#fcfcfb", "forecast": "#f0efec"}

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "font.size": 10,
    "axes.edgecolor": INK["axis"],
    "axes.labelcolor": INK["secondary"],
    "axes.titlesize": 11,
    "axes.titleweight": "semibold",
    "axes.titlecolor": INK["primary"],
    "axes.titlelocation": "left",
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": INK["grid"],
    "grid.linewidth": 0.8,
    "grid.linestyle": "-",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.color": INK["muted"],
    "ytick.color": INK["muted"],
    "xtick.labelcolor": INK["secondary"],
    "ytick.labelcolor": INK["secondary"],
    "legend.frameon": False,
    "legend.fontsize": 9,
    "lines.linewidth": 2,
    "lines.solid_capstyle": "round",
    "lines.solid_joinstyle": "round",
    "figure.facecolor": INK["surface"],
    "axes.facecolor": INK["surface"],
    "savefig.facecolor": INK["surface"],
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
})


def _x(index: pd.PeriodIndex) -> np.ndarray:
    return np.array([p.year + (p.quarter - 1) / 4 for p in index])


def _quarter_ticks(ax, start: pd.Period, end: pd.Period):
    years = range(start.year, end.year + 1)
    ax.set_xticks([y for y in years])
    ax.set_xticklabels([f"{y}" for y in years])
    ax.set_xlim(start.year + (start.quarter - 1) / 4 - 0.1, end.year + (end.quarter - 1) / 4 + 0.1)


def line_panel(ax, series: dict[str, pd.Series], title: str, first_fore: pd.Period | None = None,
               target: float | None = None, target_label: str | None = None, unit: str = "",
               rng: tuple[str, str] | None = None, bands: list[tuple[pd.Series, pd.Series, str]] | None = None,
               end_labels: bool = True, fmt: str = "{:.1f}"):
    """One panel: several series (fixed colour order), forecast shading, optional target line and fan bands."""
    start = pd.Period(rng[0], "Q") if rng else min(s.index.min() for s in series.values())
    end = pd.Period(rng[1], "Q") if rng else max(s.index.max() for s in series.values())
    if first_fore is not None:
        ax.axvspan(_x(pd.PeriodIndex([first_fore]))[0] - 0.125, _x(pd.PeriodIndex([end]))[0] + 0.125,
                   color=INK["forecast"], zorder=0, lw=0)
    for lo, hi, colour in bands or []:
        lo, hi = lo.loc[start:end], hi.loc[start:end]
        ax.fill_between(_x(lo.index), lo.values, hi.values, color=colour, lw=0, zorder=1)
    if target is not None:
        ax.axhline(target, color=INK["secondary"], lw=1, zorder=2)
        if target_label:
            ax.annotate(target_label, xy=(1, target), xycoords=("axes fraction", "data"),
                        xytext=(0, 3), textcoords="offset points", ha="right", va="bottom",
                        color=INK["secondary"], fontsize=8)
    for i, (name, s) in enumerate(series.items()):
        s = s.loc[start:end].dropna()
        ax.plot(_x(s.index), s.values, color=SERIES[i], label=name, zorder=3 + i)
    if end_labels and len(series) <= 4:
        for i, (name, s) in enumerate(series.items()):
            s = s.loc[start:end].dropna()
            if len(s):
                ax.plot(_x(s.index[-1:]), s.values[-1:], "o", ms=5, color=SERIES[i], mec=INK["surface"], mew=1.5, zorder=10)
    ax.set_title(title + (f", {unit}" if unit else ""))
    _quarter_ticks(ax, start, end)
    if len(series) >= 2:
        ax.legend(loc="best")
    return ax


def save(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def grid(nrows, ncols, width=11, height=6.2):
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height))
    fig.subplots_adjust(hspace=0.45, wspace=0.22)
    return fig, np.atleast_1d(axes).ravel()
