"""Export all ep5studio film looks as .cube, fit to HQ curves, and build a
complete film library report. Shows which looks are well-suited to the chroma
curve mechanism (low error) vs. which need the full 3D runtime."""
import sys, json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ep5studio import filmlooks
from ep5studio.cube import Cube
from tools.cube_to_hq import fit_cube_to_curves

LOOKS = [
    ("velvia_50", "Velvia 50 浓艳反转"),
    ("provia_100f", "Provia 100F 标准反转"),
    ("classic_chrome", "Classic Chrome 纪实"),
    ("portra_160", "Portra 160 柔人像"),
    ("portra_400", "Portra 400 暖人像"),
    ("ektar_100", "Ektar 100 鲜艳风景"),
    ("gold_200", "Gold 200 暖负片"),
    ("gold_100", "Gold 100 淡暖"),
    ("colorplus_200", "ColorPlus 200 消费负片"),
    ("ultramax_400", "UltraMax 400 高饱和消费"),
    ("superia_400", "Superia 400 富士消费"),
    ("bleach_bypass", "银留漂白"),
    ("acros", "Acros 100 细腻黑白"),
    ("tri_x_400", "Tri-X 400 报道黑白"),
    ("moriyama", "森山大道 高反差黑白"),
    ("cine_tone", "CineStill 电影色调"),
    ("cross_process", "交叉冲洗"),
    # faded requires parameters; skip
]

def main():
    g = filmlooks.grid(17)
    rgb = g.reshape(-1, 3)
    results = []
    for fn_name, label in LOOKS:
        fn = getattr(filmlooks, fn_name, None)
        if fn is None:
            print(f"  SKIP {fn_name} (not found)")
            continue
        try:
            out = np.clip(fn(rgb.copy()), 0, 1)
        except TypeError:
            print(f"  SKIP {fn_name} (needs params)")
            continue
        cube = Cube(label, 17, out.reshape(17, 17, 17, 3))
        cb_pts, cr_pts, report = fit_cube_to_curves(cube, grid_side=33)
        results.append({
            "key": fn_name, "name_zh": label,
            "mean_err": report["mean_rgb8_error"],
            "max_err": report["max_rgb8_error"],
            "pct_under_10": report["pct_under_10"],
            "cb_points": list(cb_pts), "cr_points": list(cr_pts),
            "suitability": "excellent" if report["mean_rgb8_error"] < 5 else
                          "good" if report["mean_rgb8_error"] < 10 else
                          "approximate" if report["mean_rgb8_error"] < 20 else "poor",
        })
        print(f"  {label:24s} err={report['mean_rgb8_error']:5.1f}  "
              f"<10:{report['pct_under_10']:4.0f}%  {results[-1]['suitability']}")
    
    # Sort by suitability
    results.sort(key=lambda r: r["mean_err"])
    out_path = ROOT / "build" / "film-library-report.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nLibrary report: {out_path}")
    print(f"Total: {len(results)} looks")
    excellent = sum(1 for r in results if r["suitability"] == "excellent")
    good = sum(1 for r in results if r["suitability"] == "good")
    print(f"Excellent (<5 err): {excellent}, Good (<10 err): {good}")

if __name__ == "__main__":
    main()
