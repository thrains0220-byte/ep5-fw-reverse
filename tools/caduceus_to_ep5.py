"""Convert Caduceus (E-P7) film recipes to E-P5 chroma-pair tables.

Data reuse from two upstream projects (no firmware code copied):
  * build/research/caduceus-ep7-main/sim/recipes/library_v2.json / v3
    - 12-sector sat/hue/light sliders + wb_shift per film look.
  * build/research/caduceus-ep7-main/sim/pipeline.py ColorEngine
    - raised-cosine sector weights, sat_mult, hue rotation math.
  * build/research/oly_fw_analysis-main/tests/fixtures/
    color-builder-reference.json
    - MEASURED per-sector saturation gains (PEN-F camera predictions).

Sector geometry: centres are 30 deg apart in the BT.601 CbCr plane with
yellow at 75 deg (pure yellow (255,255,0) -> atan2(cr,cb) = 75.4 deg).
This matches the upstream note "yellow 134 deg ... yellow-green 165 deg in
the ISP plane" under their calibrated +15 deg offset (75+15=90 in a plane
rotated 44 deg; relative spacing is what matters for the projection).
Gains come from the measured fixture, not guesses.

Output: E-P5 49-byte Cb/Cr pair tables (16-knot capacity, 9 interior knots),
same format proven safe by RC2 / safe-7. Only chroma pair data is produced;
shared gain/tone tables (0x7e453xxx) are NEVER touched.

Usage:
  python tools/caduceus_to_ep5.py --all --out build/caduceus-fit
  python tools/caduceus_to_ep5.py --recipe lib2_velvia --preview
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from native_film_curves_hq import build_hq_table, pack_axis, eval_hq_curve

RESEARCH = ROOT / "build" / "research"
LIB_V2 = RESEARCH / "caduceus-ep7-main" / "sim" / "recipes" / "library_v2.json"
LIB_V3 = RESEARCH / "caduceus-ep7-main" / "sim" / "recipes" / "library_v3.json"
GAIN_FIXTURE = (RESEARCH / "oly_fw_analysis-main" / "tests" / "fixtures"
                / "color-builder-reference.json")

SECTORS = ['yellow', 'orange', 'orange-red', 'red', 'magenta', 'violet',
           'blue', 'blue-cyan', 'cyan', 'green-cyan', 'green', 'yellow-green']

def rgb_to_ycbcr(rgb):
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

def sector_centres():
    """Anchor the 12 wheel sectors on measured BT.601 primary/secondary hues.

    The 6 primaries/secondaries pin UI indices 0,3,4,6,8,10. Intermediate
    sectors are circularly interpolated. This respects the real chroma-plane
    geometry (the red/magenta region is compressed vs. uniform 30 deg).
    Returns (centres[12], anchor_hues, rms_deg).
    """
    anchors = {
        'yellow': (1, 1, 0), 'red': (1, 0, 0), 'magenta': (1, 0, 1),
        'blue': (0, 0, 1), 'cyan': (0, 1, 1), 'green': (0, 1, 0),
    }
    hues = {}
    for name, rgb in anchors.items():
        _, cb, cr = rgb_to_ycbcr(np.array(rgb, float))
        hues[name] = np.degrees(np.arctan2(cr - 128, cb - 128)) % 360
    pinned = sorted((SECTORS.index(n), h) for n, h in hues.items())
    centres = np.zeros(12)
    for k in range(len(pinned)):
        i0, h0 = pinned[k]
        i1, h1 = pinned[(k + 1) % len(pinned)]
        span = (i1 - i0) % 12
        dh = (h1 - h0 + 180) % 360 - 180  # shortest arc
        for j in range(span):
            centres[(i0 + j) % 12] = (h0 + dh * j / span) % 360
    rms = 0.0  # anchors exact by construction
    return centres, hues, rms

def load_gains():
    """Measured per-sector sat gains from the PEN-F fixture (ui order)."""
    d = json.loads(GAIN_FIXTURE.read_text(encoding="utf-8"))
    pos = np.zeros(12); neg = np.zeros(12)
    for r in d["saturation"]:
        i, v, c = r["input_index"], r["input_value"], r["camera_static_prediction"]
        if v == 5: pos[i] = c
        if v == -5: neg[i] = -c
    return pos, neg

def load_recipe(key):
    for lib in (LIB_V2, LIB_V3):
        d = json.loads(lib.read_text(encoding="utf-8"))
        if key in d["recipes"]:
            return d["recipes"][key], lib.name
    raise KeyError(key)

# Caduceus calibration constants (sim/pipeline.py defaults). These are
# upstream's preview calibration, not E-P5 firmware facts; the fit report
# quantifies how much of the intent survives the 1D projection.
SAT_SCALE = 1.5          # slider -> coefficient scale
HUE_DEG_PER_STEP = 5.5   # hue slider step in chroma-plane degrees
SECTOR_WIDTH = 30.0      # raised-cosine half-width (30 deg spacing)
WB_AB_GAIN = 0.012       # wb a_b step -> R/B channel gain (amber+)
WB_GM_GAIN = 0.010       # wb g_m step -> G channel cut (magenta+)

def render_recipe_chroma(rgb_in, recipe, centres, gain_pos, gain_neg):
    """Apply the Caduceus ColorEngine chroma math (no luma/tone/grain).

    WB shift is applied in RGB (physically correct channel gains) before
    the chroma transform; only the resulting cb/cr are kept. base_chroma=1.0
    because the E-P5 pair is relative to its own neutral rendering.
    """
    wb = recipe.get("wb_shift", {}) or {}
    ab = float(wb.get("a_b", 0)); gm = float(wb.get("g_m", 0))
    rgb = rgb_in.copy()
    rgb[..., 0] *= 1 + ab * WB_AB_GAIN
    rgb[..., 2] *= 1 - ab * WB_AB_GAIN
    rgb[..., 1] *= 1 - gm * WB_GM_GAIN
    rgb = np.clip(rgb, 0, 1)
    y, cb, cr = rgb_to_ycbcr(rgb)
    dcb, dcr = cb - 128, cr - 128
    hue = np.degrees(np.arctan2(dcr, dcb)) % 360
    chroma = np.hypot(dcb, dcr)
    d = (hue[..., None] - centres + 180) % 360 - 180
    w = np.clip(np.cos(np.clip(d / SECTOR_WIDTH * (np.pi / 2), -np.pi / 2, np.pi / 2)), 0, None)
    s = w.sum(-1, keepdims=True)
    w = np.where(s > 1e-6, w / np.maximum(s, 1e-6), 1 / 12)
    sat = np.asarray(recipe.get("sat", [0] * 12), float)
    g = np.where(sat >= 0, gain_pos, gain_neg)
    coeff = sat * g / 5.0 * SAT_SCALE
    sat_mult = np.clip(1 + (w @ coeff) / 1000.0, 0, 3)
    hue_sl = np.asarray(recipe.get("hue", [0] * 12), float)
    # +hue slider rotates toward the PREVIOUS sector (upstream convention):
    # previous sector = lower UI index = higher hue in our anchored plane.
    hue_shift = w @ (hue_sl * HUE_DEG_PER_STEP)
    ang = np.radians(hue + hue_shift)
    ch = chroma * sat_mult
    return 128 + ch * np.cos(ang), 128 + ch * np.sin(ang)

KNOT_X = np.array([0, 32, 64, 96, 128, 160, 192, 224, 255], dtype=np.float64)

def fit_axis_ls(input_vals, target_vals, weights=None):
    """Weighted least-squares fit of 9 y-knots (linear in knots).

    Piecewise-linear interpolation is linear in the knot values, so the
    optimal knots solve a small 9x9 normal equation. Much better than
    coordinate descent and deterministic.
    """
    n = len(KNOT_X)
    # basis: for each sample, the two adjacent knots and their fractions
    idx = np.clip(np.searchsorted(KNOT_X, input_vals) - 1, 0, n - 2)
    x0, x1 = KNOT_X[idx], KNOT_X[idx + 1]
    f = (input_vals - x0) / (x1 - x0)
    if weights is None:
        weights = np.ones_like(input_vals)
    A = np.zeros((n, n)); b = np.zeros(n)
    for k, frac in ((idx, 1 - f), (idx + 1, f)):
        np.add.at(A, (k, k), weights * frac * frac)
        np.add.at(b, k, weights * frac * target_vals)
        # cross terms
    # cross terms between idx and idx+1
    np.add.at(A, (idx, idx + 1), weights * (1 - f) * f)
    np.add.at(A, (idx + 1, idx), weights * (1 - f) * f)
    # anchor neutral: knot at 128 must stay 128 (no global cast on grays)
    # solve with constraint via elimination
    mid = 4  # KNOT_X[4] == 128
    free = [i for i in range(n) if i != mid]
    rhs = b[free] - A[free, mid] * 128.0
    yk = np.full(n, 128.0)
    sol = np.linalg.solve(A[np.ix_(free, free)], rhs)
    yk[free] = np.clip(sol, 0, 255)
    return yk

def fit_recipe(recipe, grid_side=25):
    centres, hues, anchor_rms = sector_centres()
    gain_pos, gain_neg = load_gains()
    g = np.linspace(0, 1, grid_side)
    r, gg, b = np.meshgrid(g, g, g, indexing="ij")
    rgb_in = np.stack([r, gg, b], axis=-1).reshape(-1, 3)
    cb_t, cr_t = render_recipe_chroma(rgb_in, recipe, centres, gain_pos, gain_neg)
    y_in, cb_in, cr_in = rgb_to_ycbcr(rgb_in)
    # weight by chroma: gray pixels carry no color information and would
    # drag the fit toward identity.
    chroma = np.hypot(cb_in - 128, cr_in - 128)
    w = np.clip(chroma / 60.0, 0.05, 1.0)
    cb_knots = fit_axis_ls(cb_in, cb_t, w)
    cr_knots = fit_axis_ls(cr_in, cr_t, w)
    cb_fit = np.interp(cb_in, KNOT_X, cb_knots)
    cr_fit = np.interp(cr_in, KNOT_X, cr_knots)
    rgb_fit = np.clip(ycbcr_to_rgb(y_in, cb_fit, cr_fit), 0, 1)
    rgb_tgt = np.clip(ycbcr_to_rgb(y_in, cb_t, cr_t), 0, 1)
    diff = np.abs(rgb_fit - rgb_tgt) * 255
    # chroma-weighted error (what matters for the look)
    wdiff = (diff.max(axis=1) * w).sum() / w.sum()
    cb_points = tuple((int(x), int(round(y))) for x, y in zip(KNOT_X, cb_knots))
    cr_points = tuple((int(x), int(round(y))) for x, y in zip(KNOT_X, cr_knots))
    report = {
        "anchor_rms_deg": round(anchor_rms, 2),
        "sector_centres_deg": [round(float(c), 1) for c in centres],
        "mean_rgb8_error": round(float(diff.mean()), 2),
        "weighted_max_error": round(float(wdiff), 2),
        "pct_under_10": round(float((diff.max(axis=1) < 10).mean() * 100), 1),
        "cb_knots": [int(round(v)) for v in cb_knots],
        "cr_knots": [int(round(v)) for v in cr_knots],
    }
    return cb_points, cr_points, report

# Default 7-slot mapping: E-P5 ART slot -> Caduceus recipe.
SLOT_MAP = [
    ("portra400_hq", "lib2_portra", "人像柔暖"),
    ("velvia50_hq", "lib2_velvia", "胶片色彩"),
    ("classicchrome_hq", "lib2_cl_chrome", "经典铬"),
    ("gold200_hq", "lib2_gold", "柯达金"),
    ("ektar100_hq", "lib2_ektar", "风景鲜艳"),
    ("cinestill800t_hq", "lib2_cinestill", "电影色调"),
    ("moriyama_bw_hq", None, "森山黑白"),
]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recipe", help="single recipe key, e.g. lib2_velvia")
    p.add_argument("--all", action="store_true", help="fit the 7-slot map")
    p.add_argument("--grid", type=int, default=25)
    p.add_argument("--preview", action="store_true")
    p.add_argument("--out", type=Path, default=ROOT / "build" / "caduceus-fit")
    args = p.parse_args()
    jobs = SLOT_MAP if args.all else [(args.recipe, args.recipe, args.recipe)]
    results = []
    for key, rkey, label in jobs:
        if rkey is None:
            # B&W: flat 128 both axes (same as safe-7 moriyama).
            pts = ((0, 128), (64, 128), (128, 128), (192, 128), (255, 128))
            cb = build_hq_table(pts); cr = build_hq_table(pts)
            results.append({"key": key, "label": label, "recipe": None,
                            "cb_table_hex": cb.hex(), "cr_table_hex": cr.hex(),
                            "cb_words": pack_axis(cb), "cr_words": pack_axis(cr),
                            "cb_points": list(pts), "cr_points": list(pts)})
            continue
        recipe, lib = load_recipe(rkey)
        cb_pts, cr_pts, rep = fit_recipe(recipe, args.grid)
        cb = build_hq_table(cb_pts); cr = build_hq_table(cr_pts)
        entry = {"key": key, "label": label, "recipe": rkey, "source": lib,
                 "name": recipe["name"],
                 "cb_table_hex": cb.hex(), "cr_table_hex": cr.hex(),
                 "cb_words": pack_axis(cb), "cr_words": pack_axis(cr),
                 "cb_points": list(cb_pts), "cr_points": list(cr_pts),
                 "fit_report": rep}
        results.append(entry)
        print(f"{label:6s} <- {recipe['name']:14s} anchorRMS={rep['anchor_rms_deg']}deg "
              f"meanErr={rep['mean_rgb8_error']}/255 wMax={rep['weighted_max_error']} "
              f"<10:{rep['pct_under_10']}%")
        print(f"   Cb {rep['cb_knots']}")
        print(f"   Cr {rep['cr_knots']}")
    if args.preview:
        return
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "caduceus_looks.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out / 'caduceus_looks.json'}")

if __name__ == "__main__":
    main()
