"""Film-character chroma curves v2: mid-tone response + warm/cool separation.

Diagnosis (2026-11-14, real E-P5 captures): 84% of pixels have chroma < 20
(Cb deviation median ~8/128). The v1 Caduceus-fit curves had slope ~1.0 at
the neutral point, so almost the whole image was untouched -> 'digital, not
film'. Real film dye layers respond from low-mid saturation and split warm
highlights from cool shadows.

This module shapes the Cb/Cr pair so that:
  * gain engages from low deviation (knots at 16/32/48 carry real slope),
  * Cb and Cr are asymmetric (warm/cool cast per film stock),
  * highlights roll off (protect from clipping), shadows desaturate slightly.

Design references (reused, not reinvented):
  * Caduceus sim/effects.py subtractive_saturation (dye-like, neutrals safe)
  * Caduceus recipe wb_shift / per-sector intent (library_v2.json)
  * Real film split-toning: Portra warm highs/cool shadows, Velvia dense cool
    greens + warm reds, Gold warm overall, Cl.Chrome muted cool.

Still pure 49-byte pair data (RC2/safe-7 safe mechanism). No shared gain/tone
tables touched. Output feeds build_safe_full.py --looks.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from native_film_curves_hq import build_hq_table, pack_axis

# 11 knots: dense in the low-mid region where real pixels live.
X = np.array([0, 16, 32, 48, 64, 96, 128, 160, 192, 224, 255], float)

def shape(dev_gain_lo, dev_gain_mid, dev_gain_hi, asym, rolloff):
    """Build a Cb or Cr knot vector.

    dev_gain_*: chroma gain at low(|dev|~16), mid(~48), high(~96) deviation.
    asym: signed offset added to the positive side (warm/cool split).
    rolloff: highlight gain multiplier (<1 protects highs).
    Neutral 128 stays 128. Curve is monotone and clamped 0..255.
    """
    # deviation positions relative to 128
    d = X - 128  # -128..127
    # piecewise gain as function of |dev|
    ad = np.abs(d)
    g = np.interp(ad, [0, 16, 48, 96, 128],
                  [1.0, dev_gain_lo, dev_gain_mid, dev_gain_hi, dev_gain_hi * rolloff])
    y = 128 + d * g
    # asymmetric cast: positive deviations shifted (warm/cool)
    y = y + np.where(d > 0, asym, -asym * 0.4)
    # keep neutral exact
    y[X == 128] = 128
    return np.clip(y, 0, 255)

# Per-film shaping parameters. (lo, mid, hi gain, asym, rolloff) per axis.
# asym>0 on Cr = warm reds; asym<0 on Cb = cool (blue) push.
FILMS = {
    "velvia50_hq": {
        "label": "胶片色彩", "recipe": "Velvia",
        "cb": (1.18, 1.30, 1.34, -3.0, 0.92),   # dense, slightly cool blues
        "cr": (1.20, 1.34, 1.40, +4.0, 0.92),   # vivid warm reds
    },
    "portra400_hq": {
        "label": "人像柔暖", "recipe": "Portra400",
        "cb": (0.90, 0.84, 0.80, -2.0, 0.90),   # muted, cool shadows
        "cr": (0.94, 0.90, 0.86, +3.5, 0.92),   # warm skin, gentle
    },
    "gold200_hq": {
        "label": "柯达金", "recipe": "Gold200",
        "cb": (1.02, 1.00, 0.92, -1.5, 0.90),   # cyan skies muted
        "cr": (1.14, 1.18, 1.16, +5.0, 0.92),   # golden warm
    },
    "classicchrome_hq": {
        "label": "经典铬", "recipe": "Cl.Chrome",
        "cb": (0.86, 0.78, 0.72, +1.0, 0.88),   # muted, slight cool
        "cr": (0.88, 0.80, 0.74, -1.0, 0.88),   # documentary desat
    },
    "ektar100_hq": {
        "label": "风景鲜艳", "recipe": "Ektar100",
        "cb": (1.14, 1.24, 1.30, -2.0, 0.92),   # saturated blues
        "cr": (1.16, 1.28, 1.34, +3.0, 0.92),   # saturated reds
    },
    "cinestill800t_hq": {
        "label": "电影色调", "recipe": "CineStill800",
        "cb": (1.10, 1.16, 1.18, +2.0, 0.92),   # cool tungsten blue
        "cr": (0.92, 0.88, 0.84, -2.0, 0.90),   # restrained reds, halation-ish
    },
}

def build_film(key):
    f = FILMS[key]
    cb_y = shape(*f["cb"]); cr_y = shape(*f["cr"])
    cb_pts = tuple((int(x), int(round(y))) for x, y in zip(X, cb_y))
    cr_pts = tuple((int(x), int(round(y))) for x, y in zip(X, cr_y))
    cb = build_hq_table(cb_pts); cr = build_hq_table(cr_pts)
    return {"key": key, "label": f["label"], "recipe": f["recipe"],
            "cb_table_hex": cb.hex(), "cr_table_hex": cr.hex(),
            "cb_words": pack_axis(cb), "cr_words": pack_axis(cr),
            "cb_points": list(cb_pts), "cr_points": list(cr_pts)}

def build_bw():
    pts = ((0, 128), (64, 128), (128, 128), (192, 128), (255, 128))
    cb = build_hq_table(pts); cr = build_hq_table(pts)
    return {"key": "moriyama_bw_hq", "label": "森山黑白", "recipe": "bw",
            "cb_table_hex": cb.hex(), "cr_table_hex": cr.hex(),
            "cb_words": pack_axis(cb), "cr_words": pack_axis(cr),
            "cb_points": list(pts), "cr_points": list(pts)}

def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=ROOT / "build" / "film-v2")
    args = p.parse_args()
    results = [build_film(k) for k in FILMS] + [build_bw()]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "caduceus_looks.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for e in results:
        cb = [y for _, y in e["cb_points"]]; cr = [y for _, y in e["cr_points"]]
        print(f"{e['label']:6s} Cb{cb} Cr{cr}")
    print("wrote", args.out / "caduceus_looks.json")

if __name__ == "__main__":
    main()
