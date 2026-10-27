"""Charts for slides (static PNG). Palette and mark specs follow the team's dataviz rules:
fixed categorical order, 2px lines, hairline solid grid, legend for >= 2 series, text in ink colours.

Helpers: grid() makes a figure with n panels; line_panel() plots quarterly series with a shaded forecast area from
`first_fore`, optional target line and fan bands; monthly_panel() the same for monthly data; bar_panel() bars with
value labels; save() writes the PNG with a source note under the chart. Every chart in results/figures is built
through these, so one style applies to the whole deck."""
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
       "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#ffffff", "forecast": "#f0efec"}

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
               end_labels: bool = True, fmt: str = "{:.1f}", shared_history: bool = False):
    """One panel: several series (fixed colour order), forecast shading, optional target line and fan bands.

    shared_history: series share the same past (scenarios) — draw it once in ink, colours only on the forecast."""
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
    if shared_history and first_fore is not None:
        h = next(iter(series.values())).loc[start:first_fore - 1].dropna()
        ax.plot(_x(h.index), h.values, color=INK["primary"], label="Факт / оцінка", zorder=3)
        series = {k: v.loc[first_fore - 1:] for k, v in series.items()}
    for i, (name, s) in enumerate(series.items()):
        s = s.loc[start:end].dropna()
        ax.plot(_x(s.index), s.values, color=SERIES[i], label=name, zorder=4 + i)
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


def _data_points(ax, r):
    """Display coordinates of everything plotted in data units on `ax` (lines densified, bar and marker boxes),
    used to test whether a legend sits on top of the data. Reference lines in axes units (axhline, axvspan) and
    shaded bands are ignored: a legend over them stays readable."""
    from matplotlib.collections import PathCollection
    from matplotlib.patches import Rectangle
    pts, boxes = [], []
    for ln in ax.lines:
        if not ln.get_visible() or ln.get_transform() != ax.transData:
            continue
        xy = np.asarray(ln.get_xydata(), float)
        xy = xy[np.isfinite(xy).all(axis=1)]
        if len(xy) == 0:
            continue
        if len(xy) > 1:   # densify the segments so that a line crossing the legend is caught between its vertices
            xy = np.vstack([np.linspace(a, b, 12) for a, b in zip(xy[:-1], xy[1:])])
        pts.append(ax.transData.transform(xy))
    for pa in ax.patches:
        if isinstance(pa, Rectangle) and pa.get_transform() == ax.transData and pa.get_visible() and pa.get_height():
            boxes.append(pa.get_window_extent(r))
    for col in ax.collections:
        if isinstance(col, PathCollection) and col.get_offset_transform() == ax.transData:
            off = np.asarray(col.get_offsets(), float)
            if len(off):
                pts.append(ax.transData.transform(off))
    return (np.vstack(pts) if pts else np.empty((0, 2))), boxes


def _legend_hits(ax, leg, r):
    bb = leg.get_window_extent(r).expanded(1.04, 1.08)
    pts, boxes = _data_points(ax, r)
    inside = ((pts[:, 0] >= bb.x0) & (pts[:, 0] <= bb.x1) & (pts[:, 1] >= bb.y0) & (pts[:, 1] <= bb.y1)).sum() if len(pts) else 0
    return int(inside) + sum(bb.overlaps(b) for b in boxes)


def tidy(fig):
    """Collision guard run on every chart before saving (deck rule: nothing may sit on top of anything):
    1) a panel title wider than its panel is wrapped, so it cannot run into the next panel;
    2) tick labels that touch their neighbours are thinned (every 2nd, 3rd, ... label kept);
    3) a legend lying on the data is moved to the free corner; if there is none and the panel is in the bottom row,
       it goes under the panel."""
    import textwrap
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    for ax in fig.axes:
        # titles are left-aligned (rcParams), i.e. they live in ax._left_title, not in ax.title
        for t in (ax._left_title, ax.title, ax._right_title):
            if t.get_text():
                aw, tw = ax.get_window_extent(r).width, t.get_window_extent(r).width
                if tw > aw:
                    chars = max(12, int(len(t.get_text()) * aw / tw * 0.95))
                    t.set_text("\n".join(textwrap.wrap(t.get_text(), chars)))
        # reference-line labels ('ціль 5%') placed on the data are moved to a free end of the line, above or below
        for ann in [a for a in ax.texts if hasattr(a, "xyann") and isinstance(getattr(a, "xycoords", None), tuple)
                    and "axes fraction" in a.xycoords]:
            def hits(a=ann):
                fig.canvas.draw()
                bb = a.get_window_extent(r)
                pts, _ = _data_points(ax, r)
                return int(((pts[:, 0] >= bb.x0) & (pts[:, 0] <= bb.x1) & (pts[:, 1] >= bb.y0) &
                            (pts[:, 1] <= bb.y1)).sum()) if len(pts) else 0
            if hits() == 0:
                continue
            y0 = ann.xy[1]
            options = [((1, y0), (0, 3), "right", "bottom"), ((1, y0), (0, -3), "right", "top"),
                       ((0.01, y0), (0, -3), "left", "top"), ((0.01, y0), (0, 3), "left", "bottom")]
            scored = []
            for xy, off, ha, va in options:
                ann.xy, ann.xyann = xy, off
                ann.set_ha(ha); ann.set_va(va)
                scored.append((hits(), xy, off, ha, va))
                if scored[-1][0] == 0:
                    break
            _, xy, off, ha, va = min(scored, key=lambda z: z[0])
            ann.xy, ann.xyann = xy, off
            ann.set_ha(ha); ann.set_va(va)
        for axis, setter in ((ax.xaxis, ax.set_xticks), (ax.yaxis, ax.set_yticks)):
            lo, hi = sorted(axis.get_view_interval())
            ticks = [(loc, lab) for loc, lab in zip(axis.get_ticklocs(), axis.get_ticklabels())
                     if lo - 1e-9 <= loc <= hi + 1e-9 and lab.get_text()]
            if len(ticks) < 3:
                continue
            ext = [lab.get_window_extent(r) for _, lab in ticks]
            horiz = axis is ax.xaxis
            def clash(step):
                kept = ext[::step]
                return any((a.x1 + 3 > b.x0) if horiz else (a.y1 + 1 > b.y0) for a, b in zip(kept[:-1], kept[1:]))
            step = 1
            while step < len(ticks) and clash(step):
                step += 1
            if step > 1:
                keep = ticks[::step]
                setter([loc for loc, _ in keep], [lab.get_text() for _, lab in keep])
        leg = ax.get_legend()
        if leg is None:
            continue
        fig.canvas.draw()
        if _legend_hits(ax, leg, r) == 0:
            continue
        handles, labels = leg.legend_handles, [tx.get_text() for tx in leg.get_texts()]
        fs = leg.get_texts()[0].get_fontsize() if leg.get_texts() else 9
        best = None
        for loc in ("upper left", "upper right", "lower left", "lower right", "center left", "center right",
                    "upper center", "lower center"):
            cand = ax.legend(handles, labels, loc=loc, fontsize=fs)
            fig.canvas.draw()
            hits = _legend_hits(ax, cand, r)
            if best is None or hits < best[0]:
                best = (hits, loc)
            if hits == 0:
                break
        if best[0] > 0 and ax.get_subplotspec() is not None and ax.get_subplotspec().is_last_row():
            fig.canvas.draw()
            lab_bottom = min([tl.get_window_extent(r).y0 for tl in ax.get_xticklabels() if tl.get_text()] or
                             [ax.get_window_extent(r).y0])
            y = ax.transAxes.inverted().transform((0, lab_bottom))[1] - 0.04
            ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, y), ncol=min(len(labels), 3),
                      fontsize=min(fs, 8.5))
        else:
            ax.legend(handles, labels, loc=best[1], fontsize=fs)


def save(fig, path, source: str | None = None):
    """Save a figure; `source` adds a muted 'Джерело: ...' line under the chart (as in NBU reports). Runs `tidy`
    first and puts the source line under the lowest element (a legend moved under a panel included)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tidy(fig)
    if source:
        fig.canvas.draw()
        bb = fig.get_tightbbox(fig.canvas.get_renderer())        # inches
        h = fig.get_size_inches()[1]
        fig.text(0.01, (bb.y0 - 0.06) / h, f"Джерело: {source}", fontsize=8, color=INK["muted"], ha="left", va="top")
    fig.savefig(path)
    plt.close(fig)
    return path


def monthly_panel(ax, series: dict[str, pd.Series], title: str, unit: str = "", target: float | None = None,
                  target_label: str | None = None, markers: bool = False, start: str | None = None):
    """Monthly lines (PeriodIndex 'M'), fixed colour order, optional target line, end-point dots."""
    for i, (name, s) in enumerate(series.items()):
        if start:
            s = s.loc[start:]
        valid = s.dropna()
        if markers:
            ax.plot(valid.index.to_timestamp(), valid.values, color=SERIES[i], label=name, marker="o", ms=4,
                    mec=INK["surface"], mew=1)
        else:
            # full monthly range so that gaps in the data break the line instead of being bridged
            full = s.reindex(pd.period_range(valid.index.min(), valid.index.max(), freq="M"))
            ax.plot(full.index.to_timestamp(), full.values, color=SERIES[i], label=name)
            ax.plot(valid.index[-1:].to_timestamp(), valid.values[-1:], "o", ms=5, color=SERIES[i],
                    mec=INK["surface"], mew=1.5)
    if target is not None:
        ax.axhline(target, color=INK["secondary"], lw=1)
        if target_label:
            ax.annotate(target_label, xy=(1, target), xycoords=("axes fraction", "data"), xytext=(0, 3),
                        textcoords="offset points", ha="right", va="bottom", color=INK["secondary"], fontsize=8)
    ax.set_title(title + (f", {unit}" if unit else ""))
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m.%y"))
    if len(series) >= 2:
        ax.legend(loc="best")
    return ax


def bar_panel(ax, s: pd.Series, title: str, unit: str = "", colour: str | None = None, labels=None,
              value_fmt: str | None = None, highlight: dict | None = None):
    """Columns grow from a single baseline; 2px surface gap between neighbours; optional value labels."""
    x = np.arange(len(s))
    colours = [highlight.get(k, colour or SERIES[0]) if highlight else (colour or SERIES[0]) for k in s.index]
    ax.bar(x, s.values, width=0.7, color=colours, edgecolor=INK["surface"], linewidth=1.5, zorder=3)
    ax.axhline(0, color=INK["axis"], lw=1, zorder=4)
    ax.set_xticks(x)
    ax.set_xticklabels(labels if labels is not None else [str(i) for i in s.index], fontsize=8)
    ax.grid(axis="x", visible=False)
    if value_fmt:
        for xi, v in zip(x, s.values):
            if not np.isnan(v):
                ax.annotate(value_fmt.format(v), (xi, v), xytext=(0, 3 if v >= 0 else -10), textcoords="offset points",
                            ha="center", fontsize=8, color=INK["secondary"])
    ax.set_title(title + (f", {unit}" if unit else ""))
    return ax


def grid(nrows, ncols, width=11, height=6.2):
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height))
    fig.subplots_adjust(hspace=0.45, wspace=0.22)
    return fig, np.atleast_1d(axes).ravel()
