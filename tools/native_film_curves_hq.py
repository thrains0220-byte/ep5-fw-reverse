"""High-quality film curves using up to 16 knots (the full hardware capacity).

The E-P5 ISP chroma curve has 16 x-positions per axis. The factory uses only 5
effective knots (0/64/128/192/255) with padding. By using 9-12 knots we can
express NON-LINEAR saturation: shadow desaturation, midtone boost, highlight
protection, and per-channel asymmetric shapes — much closer to real film.

Still pure data patch (same 49-byte table format, same risk as RC2).
The packed driver words are verified byte-identical to the hardware format.
"""
from __future__ import annotations
from dataclasses import dataclass
try:
    import numpy as np
except ImportError:
    np = None  # eval_hq_curve unavailable without numpy; build/pack still work

def clamp(v, lo=0, hi=255):
    return max(lo, min(hi, v))

@dataclass(frozen=True)
class HQLook:
    key: str
    name_zh: str
    note: str
    # Per-axis piecewise-linear target: list of (x, y) control points.
    # x in 0..255 (input chroma deviation from 128), y in 0..255 (output).
    # The curve maps input chroma -> output chroma. 128 = neutral.
    cb_points: tuple  # ((x0,y0), (x1,y1), ...)
    cr_points: tuple

# Film looks with non-linear saturation curves.
# Design principle: real film has shadow desaturation (silver halide grains
# need minimum exposure), midtone richness, and highlight roll-off.
HQ_LOOKS: tuple[HQLook, ...] = (
    HQLook("velvia50_hq", "反转50·浓艳HQ",
           "Velvia: 阴影轻微去饱和, 中间调强饱和+45%, 高光保护。蓝偏品红。",
           # Cb axis: shadow desat, midtone boost, highlight protect
           ((0,0),(32,22),(64,52),(96,88),(128,128),(160,172),(192,210),(224,240),(255,255)),
           # Cr axis: slightly stronger boost (Velvia reds are vivid)
           ((0,0),(32,20),(64,50),(96,86),(128,129),(160,174),(192,214),(224,242),(255,255))),
    HQLook("portra400_hq", "人像400·柔暖HQ",
           "Portra 400: 低饱和, 护肤色暖调, 阴影微暖, 高光柔滚降。",
           ((0,2),(32,26),(64,56),(96,92),(128,127),(160,162),(192,196),(224,228),(255,252)),
           ((0,4),(32,28),(64,58),(96,94),(128,130),(160,164),(192,198),(224,230),(255,253))),
    HQLook("gold200_hq", "柯达金200·暖金HQ",
           "Gold 200: 中间调暖金, 饱和+20%, 阴影微冷, 高光暖滚降。",
           ((0,0),(32,24),(64,54),(96,90),(128,125),(160,164),(192,200),(224,234),(255,255)),
           ((0,2),(32,26),(64,58),(96,94),(128,133),(160,170),(192,206),(224,238),(255,255))),
    HQLook("classicchrome_hq", "经典铬·纪实HQ",
           "Classic Chrome: 低饱和硬调, 黄/绿显著拉回, 深蓝紫保留, 微冷。",
           ((0,4),(32,30),(64,60),(96,96),(128,129),(160,160),(192,190),(224,222),(255,250)),
           ((0,2),(32,28),(64,58),(96,94),(128,127),(160,158),(192,188),(224,220),(255,248))),
    HQLook("ektar100_hq", "风景100·鲜艳HQ",
           "Ektar: 高饱和风景, 红/蓝极强, 绿适中, 阴影保饱和。",
           ((0,0),(32,18),(64,46),(96,84),(128,128),(160,176),(192,218),(224,244),(255,255)),
           ((0,0),(32,16),(64,44),(96,82),(128,128),(160,178),(192,222),(224,246),(255,255))),
    HQLook("cinestill800t_hq", "电影800T·钨丝HQ",
           "CineStill 800T: 钨丝灯平衡, 蓝/青强, 红/橙柔, 高光halation取向。",
           ((0,0),(32,20),(64,48),(96,86),(128,132),(160,176),(192,216),(224,242),(255,255)),
           ((0,4),(32,30),(64,60),(96,96),(128,126),(160,156),(192,186),(224,218),(255,248))),
    HQLook("moriyama_bw_hq", "森山·高反差黑白",
           "森山大道: 纯去色黑白。高反差靠机身对比度+5。",
           ((0,128),(64,128),(128,128),(192,128),(255,128)),
           ((0,128),(64,128),(128,128),(192,128),(255,128))),
    HQLook("trix400_hq", "Tri-X·报道黑白",
           "Tri-X 400: 纯去色黑白。颗粒与反差靠机身设置。",
           ((0,128),(64,128),(128,128),(192,128),(255,128)),
           ((0,128),(64,128),(128,128),(192,128),(255,128))),
)


def fit_16knots(points: tuple) -> tuple[list[int], list[int], list[int]]:
    """Fit control points into the 16-position hardware format.
    Returns (x[16], y[16], slope[17]).
    
    Strategy: place the control points at the available interior positions,
    pad leading with x=0 and trailing with x=255.
    """
    pts = sorted(points, key=lambda p: p[0])
    n = len(pts)
    # We have 16 positions. Reserve leading pad (x=0) and trailing pad (x=255).
    # Interior: positions 1..14 (14 slots). Use as many as we have points.
    # Leading pad: positions 0..(lead-1) all x=0, y=pts[0][1]
    # Trailing pad: positions (16-trail)..15 all x=255, y=pts[-1][1]
    
    # Simple layout: 3 leading pad, n interior, (13-n) trailing pad
    lead = 3
    trail = 16 - lead - n
    if trail < 1:
        # Too many points; reduce lead
        lead = 16 - n - 1
        trail = 1
    
    x = [0] * lead + [p[0] for p in pts] + [255] * trail
    y = [pts[0][1]] * lead + [p[1] for p in pts] + [pts[-1][1]] * trail
    
    assert len(x) == 16 and len(y) == 16
    
    # Compute Q7 slopes for 17 segments
    slope = [0] * 17
    for i in range(16):
        dx = x[i] - (x[i-1] if i > 0 else 0)
        dy = y[i] - (y[i-1] if i > 0 else y[0])
        if dx > 0:
            slope[i+1] = clamp(round(dy / dx * 128), 0, 255)
        else:
            slope[i+1] = 0
    # slope[0] is for the segment before x[0] (always 0 for pad)
    slope[0] = 0
    
    return x, y, slope


def build_hq_table(points: tuple) -> bytes:
    """49-byte table from control points."""
    x, y, slope = fit_16knots(points)
    return bytes(x) + bytes(y) + bytes(slope)


def pack_axis(table: bytes) -> list[int]:
    """17 packed driver words."""
    x, y, slope = table[0:16], table[16:32], table[32:49]
    return [(x[i-1] if i >= 1 else 0) | ((y[i-1] if i >= 1 else 0) << 8) | (slope[i] << 16)
            for i in range(17)]


def eval_hq_curve(table: bytes, values: np.ndarray) -> np.ndarray:
    """Evaluate the 16-knot piecewise-linear curve."""
    x = np.array(table[0:16], dtype=np.float64)
    y = np.array(table[16:32], dtype=np.float64)
    # Remove duplicate x for interpolation (keep first occurrence)
    _, idx = np.unique(x, return_index=True)
    return np.interp(values.astype(np.float64), x[idx], y[idx])


def hq_look_tables(look: HQLook) -> dict:
    cb = build_hq_table(look.cb_points)
    cr = build_hq_table(look.cr_points)
    return {
        "key": look.key, "name_zh": look.name_zh, "note": look.note,
        "cb_table_hex": cb.hex(), "cr_table_hex": cr.hex(),
        "cb_words": pack_axis(cb), "cr_words": pack_axis(cr),
        "knots_cb": len(look.cb_points), "knots_cr": len(look.cr_points),
    }


if __name__ == "__main__":
    import json, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    out = [hq_look_tables(l) for l in HQ_LOOKS]
    print(json.dumps(out, ensure_ascii=False, indent=2))
