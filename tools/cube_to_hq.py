"""Import any .cube 3D LUT and fit it to E-P5 HQ 9-knot chroma curves.

Projects the full 3D LUT onto the two 1D chroma axes (Cb, Cr) that the E-P5
ISP hardware can express. Uses least-squares optimization over 9 knot positions
to minimize the perceptual color error. Reports what fraction of the LUT's
intent is captured vs. what requires the full 3D runtime (hue rotation, luma
curves, split toning).

Usage:
  python tools/cube_to_hq.py input.cube --name "My Film" --out build/film-custom
  python tools/cube_to_hq.py input.cube --preview  # show error report only

The output is a look-report.json compatible with build_neutral_trio_hq.py.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ep5studio.cube import parse_cube, sample_cube

# BT.601 full-range YCbCr (matches E-P5 ISP)
def rgb_to_ycbcr(rgb):
    """rgb: [...,3] float 0..1 -> (Y, Cb, Cr) each 0..255"""
    r, g, b = rgb[..., 0] * 255, rgb[..., 1] * 255, rgb[..., 2] * 255
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    return y, cb, cr

def ycbcr_to_rgb(y, cb, cr):
    dcb, dcr = cb - 128, cr - 128
    r = y + 1.402 * dcr
    g = y - 0.344136 * dcb - 0.714136 * dcr
    b = y + 1.772 * dcb
    return np.stack([r, g, b], axis=-1) / 255.0

# 9 knot x-positions (input chroma 0..255)
KNOT_X = np.array([0, 32, 64, 96, 128, 160, 192, 224, 255], dtype=np.float64)

def fit_axis(input_vals, target_vals, n_iter=200):
    """Fit 9 y-knots minimizing MSE between interpolated curve and target.
    input_vals, target_vals: 1D arrays of chroma values (0..255).
    Returns y-knots (9 ints)."""
    # Initial: sample target at knot positions via binning
    y_knots = np.array([128.0] * 9)
    for i, x in enumerate(KNOT_X):
        mask = np.abs(input_vals - x) < 16
        if mask.sum() > 0:
            y_knots[i] = np.mean(target_vals[mask])
        else:
            y_knots[i] = x  # identity fallback
    
    # Coordinate descent
    def eval_curve(yk):
        return np.interp(input_vals, KNOT_X, yk)
    
    best_err = np.mean((eval_curve(y_knots) - target_vals) ** 2)
    for _ in range(n_iter):
        improved = False
        for i in range(9):
            for delta in (-8, -4, -2, -1, 1, 2, 4, 8):
                trial = y_knots.copy()
                trial[i] = np.clip(trial[i] + delta, 0, 255)
                err = np.mean((eval_curve(trial) - target_vals) ** 2)
                if err < best_err - 1e-6:
                    y_knots, best_err, improved = trial, err, True
        if not improved:
            break
    return [int(round(v)) for v in y_knots]

def fit_cube_to_curves(cube, grid_side=33):
    """Fit a .cube LUT to Cb/Cr 9-knot curves. Returns (cb_points, cr_points, report)."""
    # Sample on a dense sRGB grid
    g = np.linspace(0, 1, grid_side)
    r, gg, b = np.meshgrid(g, g, g, indexing="ij")
    rgb_in = np.stack([r, gg, b], axis=-1).reshape(-1, 3)
    rgb_out = np.clip(sample_cube(cube, rgb_in), 0, 1)
    
    y_in, cb_in, cr_in = rgb_to_ycbcr(rgb_in)
    y_out, cb_out, cr_out = rgb_to_ycbcr(rgb_out)
    
    # Fit each axis: input chroma -> output chroma
    cb_knots = fit_axis(cb_in, cb_out)
    cr_knots = fit_axis(cr_in, cr_out)
    
    cb_points = tuple((int(x), int(y)) for x, y in zip(KNOT_X, cb_knots))
    cr_points = tuple((int(x), int(y)) for x, y in zip(KNOT_X, cr_knots))
    
    # Error report: apply fitted curves and compare to full LUT
    cb_fit = np.interp(cb_in, KNOT_X, cb_knots)
    cr_fit = np.interp(cr_in, KNOT_X, cr_knots)
    rgb_fit = np.clip(ycbcr_to_rgb(y_in, cb_fit, cr_fit), 0, 1)
    
    diff = np.abs(rgb_fit - rgb_out) * 255
    report = {
        "grid_side": grid_side,
        "mean_rgb8_error": float(diff.mean()),
        "max_rgb8_error": float(diff.max()),
        "pct_under_5": float((diff.max(axis=1) < 5).mean() * 100),
        "pct_under_10": float((diff.max(axis=1) < 10).mean() * 100),
        "cb_knots": cb_knots,
        "cr_knots": cr_knots,
        "note": "色度曲线投影：保留饱和/偏色取向，丢失色相旋转/亮度曲线/分离调色。",
    }
    return cb_points, cr_points, report

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cube", type=Path, help="input .cube file")
    p.add_argument("--name", default=None, help="look display name")
    p.add_argument("--key", default=None, help="look key (filename stem if omitted)")
    p.add_argument("--preview", action="store_true", help="show error report only")
    p.add_argument("--grid", type=int, default=33, help="sampling grid side")
    args = p.parse_args()
    
    text = args.cube.read_bytes()
    cube = parse_cube(text)
    name = args.name or cube.title or args.cube.stem
    key = args.key or args.cube.stem.lower().replace(" ", "_")[:20]
    
    cb_points, cr_points, report = fit_cube_to_curves(cube, args.grid)
    
    print(f"Imported: {name} ({cube.side}³)")
    print(f"  Mean RGB error: {report['mean_rgb8_error']:.1f}/255")
    print(f"  Max RGB error:  {report['max_rgb8_error']:.1f}/255")
    print(f"  Pixels <5 err:  {report['pct_under_5']:.0f}%")
    print(f"  Pixels <10 err: {report['pct_under_10']:.0f}%")
    print(f"  Cb knots: {report['cb_knots']}")
    print(f"  Cr knots: {report['cr_knots']}")
    
    if args.preview:
        return
    
    # Build HQ table bytes
    sys.path.insert(0, str(ROOT / "tools"))
    from native_film_curves_hq import build_hq_table, pack_axis, HQLook
    cb_table = build_hq_table(cb_points)
    cr_table = build_hq_table(cr_points)
    
    out = {
        "key": key, "name_zh": name, "note": f"从 {args.cube.name} 导入拟合",
        "cb_table_hex": cb_table.hex(), "cr_table_hex": cr_table.hex(),
        "cb_words": pack_axis(cb_table), "cr_words": pack_axis(cr_table),
        "cb_points": list(cb_points), "cr_points": list(cr_points),
        "knots_cb": 9, "knots_cr": 9,
        "source_cube": str(args.cube), "fit_report": report,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
