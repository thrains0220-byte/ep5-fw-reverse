"""Fit film-look chroma responses to the E-P5 native per-axis curve format.

The proven RC2 mechanism patches two 49-byte hardware chroma curves (one per
Cb/Cr axis). Each curve is piecewise linear with knots at x=0,64,128,192,255
and Q7 segment slopes; 128 is neutral. This is a per-axis saturation scale plus
an optional constant chroma shift. It cannot rotate hue, change luma, or do
luma-dependent split toning -- those need the software path and are out of
scope for this hardware-curve pack.

This module:
  * defines looks as (scale, cb_shift, cr_shift) calibrated to published film
    characteristics (see docs/NATIVE_FILM_PACK.md for sources),
  * fits the five knot values per axis,
  * reports the chroma approximation error against the ideal per-axis transform
    and against the full RGB film target from ep5studio.filmlooks,
  * emits byte-correct 49-byte tables and 17-word packed driver axes.

No camera, no firmware container here; build_native_film consumes the tables.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

KNOT_X = (0, 64, 128, 192, 255)


def clamp(v, lo=0, hi=255):
    return max(lo, min(hi, v))


@dataclass(frozen=True)
class NativeLook:
    key: str
    name_zh: str
    scale: float          # chroma saturation multiplier (1.0 = identity)
    cb_shift: int         # constant Cb offset (blue-difference); + = toward yellow
    cr_shift: int         # constant Cr offset (red-difference); + = toward red
    note: str
    rgb_target: str | None = None   # ep5studio.filmlooks function name for error ref


# Calibrated to published film characteristics. Shifts are kept small so neutral
# grays stay near-neutral (real Gold/Portra keep grays gray; the warmth is in the
# colors). scale is the dominant, fully-expressible lever.
LOOKS: tuple[NativeLook, ...] = (
    NativeLook("gold200", "柯达金200·暖负片", 1.16, -3, 5,
               "暖金负片取向：饱和+16%，轻微暖偏移（Cr+5/Cb-3），灰阶近中性。"
               "亮度S曲线与分离调色不在硬件曲线范围。", "gold_200"),
    NativeLook("portra160", "人像160·柔负片", 0.90, -1, 2,
               "柔和人像负片取向：饱和-10%，极轻微暖移，保护肤色。", "portra_160"),
    NativeLook("velvia50", "反转50·浓艳", 1.42, 0, 1,
               "浓艳反转片取向：饱和+42%，近中性灰阶。高反差亮度曲线不在范围。", "velvia_50"),
    NativeLook("classicchrome", "经典铬·纪实", 0.82, 1, -1,
               "纪实低饱和取向：饱和-18%，极轻微冷移。", "classic_chrome"),
    NativeLook("ektar100", "风景100·鲜艳", 1.30, 0, 0,
               "鲜艳风景负片取向：饱和+30%，中性灰阶。", "ektar_100"),
    NativeLook("bleach", "银留·漂白", 0.55, 0, 0,
               "漂白 bypass 取向：饱和-45%，金属感低彩。亮度反差不在范围。", "bleach_bypass"),
    NativeLook("moriyama_bw", "森山·高反差黑白", 0.0, 0, 0,
               "黑白取向：完全去色（Cb/Cr→128）。森山标志性的高反差亮度S曲线"
               "无法由色度曲线表达，此版为纯去色黑白，反差靠机身对比度设置。", "moriyama"),
    NativeLook("trix_bw", "Tri-X·报道黑白", 0.0, 0, 0,
               "经典报道黑白取向：完全去色。颗粒与亮度反差不在色度曲线范围。", "tri_x_400"),
)


def axis_knots(scale: float, shift: int) -> list[int]:
    """Five output knot values at x=0,64,128,192,255.

    The ideal per-axis transform is clamp(128+shift+scale*(x-128)), a clamped
    line (flat-low / linear / flat-high). Sampling the line at the five knots
    leaves a large error where the clamp knee falls between knots, so refine the
    interior knots to minimise the max deviation from the clamped ideal over the
    whole 0..255 axis. The neutral knot (x=128) is pinned to 128+shift so grays
    keep the intended cast.
    """
    ideal = np.clip(128 + shift + scale * (np.arange(256) - 128), 0, 255)
    base = [clamp(round(128 + shift + scale * (x - 128))) for x in KNOT_X]
    if scale <= 0:
        return [clamp(128 + shift)] * 5
    # Coordinate descent on the four free knots (keep x=128 pinned).
    knots = list(base)
    xs = np.array(KNOT_X, dtype=np.float64)

    def max_err(ks):
        fit = np.interp(np.arange(256), xs, np.array(ks, dtype=np.float64))
        return float(np.abs(fit - ideal).max())

    best = max_err(knots)
    for _ in range(60):
        improved = False
        for idx in (0, 1, 3, 4):
            for delta in (-4, -2, -1, 1, 2, 4):
                trial = list(knots)
                trial[idx] = clamp(trial[idx] + delta)
                e = max_err(trial)
                if e < best - 1e-9:
                    knots, best, improved = trial, e, True
        if not improved:
            break
    return knots


def build_table(knots: list[int]) -> bytes:
    """49-byte native table: x[16], y[16], slope[17].

    Layout matches the factory curves: four leading pad knots at x=0, the five
    real knots, then pad knots at x=255. Slopes are Q7 segment slopes.
    """
    y0, y64, y128, y192, y255 = knots
    x = bytes([0] * 4 + [64, 128, 192] + [255] * 9)
    y = bytes([y0] * 4 + [y64, y128, y192] + [y255] * 9)
    # slope[i] for segment ending at real knot i (Q7). Pad segments slope 0.
    s0 = clamp(round((y64 - y0) / 64 * 128), 0, 255)
    s1 = clamp(round((y128 - y64) / 64 * 128), 0, 255)
    s2 = clamp(round((y192 - y128) / 64 * 128), 0, 255)
    s3 = clamp(round((y255 - y192) / 63 * 128), 0, 255)
    slope = bytes([0] * 4 + [s0, s1, s2, s3] + [0] * 9)
    return x + y + slope


def pack_axis(table: bytes) -> list[int]:
    """17 packed driver words: word[i] = x[i-1] | y[i-1]<<8 | slope[i]<<16."""
    x, y, slope = table[0:16], table[16:32], table[32:49]
    words = []
    for i in range(17):
        px = x[i - 1] if i >= 1 else 0
        py = y[i - 1] if i >= 1 else 0
        words.append(px | (py << 8) | (slope[i] << 16))
    return words


def eval_curve(table: bytes, values: np.ndarray) -> np.ndarray:
    """Piecewise-linear evaluation of a 49-byte table at integer inputs 0..255."""
    x = np.array([0, 64, 128, 192, 255], dtype=np.float64)
    # y array = [y0]*4 + [y64,y128,y192] + [y255]*9: real knots at indices 0,4,5,6,7.
    y = np.array([table[16 + 0], table[16 + 4], table[16 + 5], table[16 + 6], table[16 + 7]],
                 dtype=np.float64)
    return np.interp(values.astype(np.float64), x, y)


def chroma_error(look: NativeLook) -> dict:
    """Error of the fitted curve vs the ideal per-axis transform over all chroma."""
    cb_table = build_table(axis_knots(look.scale, look.cb_shift))
    cr_table = build_table(axis_knots(look.scale, look.cr_shift))
    vals = np.arange(256)
    ideal_cb = np.clip(128 + look.cb_shift + look.scale * (vals - 128), 0, 255)
    ideal_cr = np.clip(128 + look.cr_shift + look.scale * (vals - 128), 0, 255)
    fit_cb = eval_curve(cb_table, vals)
    fit_cr = eval_curve(cr_table, vals)
    dcb = np.abs(fit_cb - ideal_cb)
    dcr = np.abs(fit_cr - ideal_cr)
    return {
        "cb_max": float(dcb.max()), "cb_mean": float(dcb.mean()),
        "cr_max": float(dcr.max()), "cr_mean": float(dcr.mean()),
        "cb_knots": axis_knots(look.scale, look.cb_shift),
        "cr_knots": axis_knots(look.scale, look.cr_shift),
    }


def rgb_target_error(look: NativeLook, side: int = 17) -> dict | None:
    """Error of the hardware-curve look vs the full RGB film target on a grid.

    This measures how much of the intended film look the chroma-only hardware
    curve actually captures (luma/hue/split-tone differences show up here).
    """
    if not look.rgb_target:
        return None
    from ep5studio import filmlooks
    fn = getattr(filmlooks, look.rgb_target)
    g = np.linspace(0.0, 1.0, side)
    r, gg, b = np.meshgrid(g, g, g, indexing="ij")
    rgb = np.stack([r, gg, b], axis=-1).reshape(-1, 3)
    target = np.clip(fn(rgb.copy()), 0.0, 1.0)

    # Apply the hardware chroma curve in YCbCr (BT.601 full range), luma untouched.
    cb_table = build_table(axis_knots(look.scale, look.cb_shift))
    cr_table = build_table(axis_knots(look.scale, look.cr_shift))
    r8, g8, b8 = (rgb * 255.0).T
    y = 0.299 * r8 + 0.587 * g8 + 0.114 * b8
    cb = 128 - 0.168736 * r8 - 0.331264 * g8 + 0.5 * b8
    cr = 128 + 0.5 * r8 - 0.418688 * g8 - 0.081312 * b8
    cb2 = eval_curve(cb_table, np.clip(np.round(cb), 0, 255).astype(int))
    cr2 = eval_curve(cr_table, np.clip(np.round(cr), 0, 255).astype(int))
    dcb, dcr = cb2 - 128, cr2 - 128
    r2 = np.clip(y + 1.402 * dcr, 0, 255)
    g2 = np.clip(y - 0.344136 * dcb - 0.714136 * dcr, 0, 255)
    b2 = np.clip(y + 1.772 * dcb, 0, 255)
    got = np.stack([r2, g2, b2], axis=-1) / 255.0
    diff = np.abs(got - target) * 255.0
    return {
        "grid_side": side,
        "max_rgb8_error": float(diff.max()),
        "mean_rgb8_error": float(diff.mean()),
        "note": "色度曲线仅表达饱和/去色/微偏色；与完整RGB目标的差含亮度S曲线、"
                "色相旋转与分离调色等不可表达部分。",
    }


def look_tables(look: NativeLook) -> dict:
    cb = build_table(axis_knots(look.scale, look.cb_shift))
    cr = build_table(axis_knots(look.scale, look.cr_shift))
    return {
        "key": look.key, "name_zh": look.name_zh, "note": look.note,
        "scale": look.scale, "cb_shift": look.cb_shift, "cr_shift": look.cr_shift,
        "cb_table_hex": cb.hex(), "cr_table_hex": cr.hex(),
        "cb_words": pack_axis(cb), "cr_words": pack_axis(cr),
        "chroma_error": chroma_error(look),
        "rgb_target_error": rgb_target_error(look),
    }


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    out = [look_tables(l) for l in LOOKS]
    print(json.dumps(out, ensure_ascii=False, indent=2))
