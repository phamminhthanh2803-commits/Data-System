"""Vessel route rendering engine.

Pacific-centred projection, antimeridian-safe drawing, real sea routes
via the `searoute` library, plus a timeline panel under the map.
Outputs a 300 DPI PNG.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np
import searoute as sr
from matplotlib.patches import FancyArrowPatch

CENTRAL_LON = 180.0
WORLD_GEOJSON = Path(__file__).parent / "world.geojson"

PURPLE = "#534AB7"
PURPLE_DARK = "#332C7A"
LAND = "#EFE9E1"
LAND_EDGE = "#BFB7A8"
OCEAN = "#F6F9FC"
INK = "#1F2230"
MUTED = "#7A7D8C"


@dataclass
class Waypoint:
    month: str          # display label, e.g. "Dec 2016"
    region: str         # raw region string from input
    source: str         # "MarineTraffic", "VesselTracker", "Both", ...
    port: str           # human port name
    lon: float
    lat: float


# ---------- antimeridian helpers ----------

def shift_lon(lon):
    """Shift a longitude (or array) into the Pacific-centred frame [-180, 180)."""
    arr = np.asarray(lon, dtype=float)
    return (arr - CENTRAL_LON + 180.0) % 360.0 - 180.0


def _split_on_jumps(xs, ys, threshold=180.0):
    """Yield (xs, ys) segments, breaking wherever |dx| > threshold."""
    xs = np.asarray(xs)
    ys = np.asarray(ys)
    if len(xs) < 2:
        yield xs, ys
        return
    breaks = np.where(np.abs(np.diff(xs)) > threshold)[0] + 1
    start = 0
    for b in breaks:
        yield xs[start:b], ys[start:b]
        start = b
    yield xs[start:], ys[start:]


# ---------- world land drawing ----------

def _draw_land(ax):
    with open(WORLD_GEOJSON, "r", encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj["features"]:
        geom = feat["geometry"]
        if geom is None:
            continue
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            ring = np.array(poly[0])  # outer ring only — fine at 110m resolution
            xs = shift_lon(ring[:, 0])
            ys = ring[:, 1]
            for sx, sy in _split_on_jumps(xs, ys):
                if len(sx) >= 3:
                    ax.fill(sx, sy, color=LAND, edgecolor=LAND_EDGE, linewidth=0.4, zorder=1)


# ---------- searoute ----------

def _sea_leg(origin, dest):
    """Return shifted (xs, ys) along the maritime route between two ports."""
    feat = sr.searoute(origin, dest, units="naut")
    coords = np.array(feat["geometry"]["coordinates"])
    xs = shift_lon(coords[:, 0])
    ys = coords[:, 1]
    distance_nm = float(feat["properties"].get("length", 0.0))
    return xs, ys, distance_nm


# ---------- label grouping ----------

def _group_consecutive_same_port(wps: Sequence[Waypoint]):
    """Return list of (indices, group) where each group shares a port and is consecutive."""
    groups = []
    i = 0
    while i < len(wps):
        j = i
        while j + 1 < len(wps) and wps[j + 1].port == wps[i].port:
            j += 1
        groups.append((list(range(i, j + 1)), wps[i:j + 1]))
        i = j + 1
    return groups


def _split_month_year(label: str):
    """Best-effort split of 'Jan 2017' -> ('Jan', '2017'). Returns (label, None) if it can't."""
    parts = label.strip().rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], parts[1]
    return label.strip(), None


def _format_group_label(idx_range, group):
    nums = idx_range[0] + 1 if len(idx_range) == 1 else f"{idx_range[0] + 1}–{idx_range[-1] + 1}"
    if len(group) == 1:
        months = group[0].month
    else:
        first, last = group[0].month, group[-1].month
        f_mon, f_yr = _split_month_year(first)
        l_mon, l_yr = _split_month_year(last)
        if f_yr and l_yr and f_yr == l_yr:
            months = f"{f_mon}–{l_mon} {l_yr}"
        else:
            months = f"{first} – {last}"
    return f"{nums}. {months} / {group[0].port}"


# ---------- main render ----------

def render(waypoints: Sequence[Waypoint], out_path: str, title: str = "Hành trình tàu") -> dict:
    """Render the route to PNG. Returns metadata (legs, distances)."""
    if len(waypoints) < 2:
        raise ValueError("Cần tối thiểu 2 waypoint để vẽ tuyến.")

    fig = plt.figure(figsize=(14, 9), dpi=150)
    gs = fig.add_gridspec(2, 1, height_ratios=[5, 1], hspace=0.12)
    ax_map = fig.add_subplot(gs[0])
    ax_tl = fig.add_subplot(gs[1])

    # ---- map ----
    ax_map.set_facecolor(OCEAN)
    _draw_land(ax_map)

    # Auto-zoom to data with padding, but keep wide enough to read
    sx = shift_lon([w.lon for w in waypoints])
    ys = np.array([w.lat for w in waypoints])
    x_min, x_max = float(sx.min()) - 18, float(sx.max()) + 22
    y_min, y_max = float(ys.min()) - 12, float(ys.max()) + 14
    x_min = max(x_min, -180)
    x_max = min(x_max, 180)
    y_min = max(y_min, -75)
    y_max = min(y_max, 78)
    ax_map.set_xlim(x_min, x_max)
    ax_map.set_ylim(y_min, y_max)
    ax_map.set_aspect("equal")
    ax_map.set_xticks([])
    ax_map.set_yticks([])
    for spine in ax_map.spines.values():
        spine.set_color(LAND_EDGE)

    # ---- legs ----
    legs = []
    for a, b in zip(waypoints[:-1], waypoints[1:]):
        try:
            xs, ys_leg, dist = _sea_leg((a.lon, a.lat), (b.lon, b.lat))
        except Exception as exc:
            # Fallback: straight line on the shifted plane
            xs = np.array([shift_lon(a.lon), shift_lon(b.lon)])
            ys_leg = np.array([a.lat, b.lat])
            dist = float("nan")
            print(f"[warn] searoute failed for {a.port}->{b.port}: {exc}")
        for seg_x, seg_y in _split_on_jumps(xs, ys_leg):
            if len(seg_x) >= 2:
                ax_map.plot(seg_x, seg_y, color=PURPLE, linewidth=2.4, zorder=3,
                            solid_capstyle="round", solid_joinstyle="round")
        # Direction arrow at the midpoint of the longest continuous segment
        best = max(_split_on_jumps(xs, ys_leg), key=lambda s: len(s[0]))
        if len(best[0]) >= 4:
            mid = len(best[0]) // 2
            ax_map.add_patch(FancyArrowPatch(
                (best[0][mid - 1], best[1][mid - 1]),
                (best[0][mid + 1], best[1][mid + 1]),
                arrowstyle="-|>", mutation_scale=14, color=PURPLE_DARK, zorder=4))
        legs.append({"from": a.port, "to": b.port, "distance_nm": dist})

    # ---- markers + labels ----
    groups = _group_consecutive_same_port(waypoints)
    for idx_range, group in groups:
        wp = group[0]
        x = float(shift_lon(wp.lon))
        y = wp.lat
        ax_map.scatter([x], [y], s=110, color="white", edgecolor=PURPLE_DARK,
                       linewidth=2.0, zorder=5)
        ax_map.scatter([x], [y], s=22, color=PURPLE_DARK, zorder=6)
        label = _format_group_label(idx_range, group)
        # Offset label up-right; flip if near right edge
        dx, ha = (1.5, "left")
        if x > (x_max - 18):
            dx, ha = (-1.5, "right")
        ax_map.annotate(
            label, xy=(x, y), xytext=(x + dx, y + 2.0),
            fontsize=9, color=INK, ha=ha, va="bottom",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=LAND_EDGE, lw=0.6, alpha=0.92),
            zorder=7,
        )

    ax_map.set_title(title, fontsize=14, color=INK, pad=10, loc="left", fontweight="bold")

    # ---- timeline panel ----
    n = len(waypoints)
    ax_tl.set_xlim(0, n + 1)
    ax_tl.set_ylim(0, 1)
    ax_tl.axis("off")
    ax_tl.hlines(0.55, 0.6, n + 0.4, color=LAND_EDGE, linewidth=1.2)

    # Decide label density so things don't overlap.
    # Target: ~25 labels max for fonts at this size.
    if n <= 12:
        label_step, dot_size, month_fs, port_fs, src_fs = 1, 90, 9, 8, 7
        show_source = True
    elif n <= 25:
        label_step, dot_size, month_fs, port_fs, src_fs = 1, 60, 8, 7, 6
        show_source = True
    elif n <= 50:
        label_step, dot_size, month_fs, port_fs, src_fs = 2, 40, 7, 6, 6
        show_source = False
    else:
        label_step = max(1, n // 25)
        dot_size, month_fs, port_fs, src_fs = 22, 6, 6, 6
        show_source = False

    for i, wp in enumerate(waypoints):
        cx = i + 1
        ax_tl.scatter([cx], [0.55], s=dot_size, color=PURPLE, zorder=3)
        if i % label_step != 0 and i != n - 1:
            continue
        rot = 0 if n <= 12 else 30
        va_month = "bottom" if rot == 0 else "bottom"
        ax_tl.text(cx, 0.78, wp.month, ha="center" if rot == 0 else "left",
                   va=va_month, fontsize=month_fs, color=INK, fontweight="bold",
                   rotation=rot)
        ax_tl.text(cx, 0.40, wp.port, ha="center" if rot == 0 else "right",
                   va="top", fontsize=port_fs, color=PURPLE_DARK,
                   rotation=rot)
        if show_source and wp.source:
            ax_tl.text(cx, 0.20, wp.source, ha="center", va="top",
                       fontsize=src_fs, color=MUTED, style="italic")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return {"legs": legs, "total_nm": float(np.nansum([l["distance_nm"] for l in legs]))}
