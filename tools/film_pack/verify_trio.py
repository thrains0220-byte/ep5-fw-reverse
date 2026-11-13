"""Verify a trio firmware: only 73/106/108 chroma changes; 82/107/109 stay stock.
Pure Python (no numpy); runs under WSL with the prebuilt contract probe."""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from external.oly_fw_analysis.tools import oly_container

fw = ROOT / "build/film-trio/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
report = json.loads((ROOT / "build/film-trio/trio-report.json").read_text(encoding="utf-8"))
runner = ROOT / "build/chroma-dump/ep5-contract-probe"
build = ROOT / "build" / "trio-verify"
build.mkdir(exist_ok=True)

def pack_from_hex(h):
    t = bytes.fromhex(h)
    x, y, slope = t[0:16], t[16:32], t[32:49]
    return [(x[i-1] if i >= 1 else 0) | ((y[i-1] if i >= 1 else 0) << 8) | (slope[i] << 16) for i in range(17)]

def words(path, tag):
    main = build / (tag + ".main")
    main.write_bytes(oly_container.parse(path.read_bytes())[0].payload)
    out = subprocess.run([str(runner), str(main), "chroma"], capture_output=True, text=True, timeout=30)
    if out.returncode:
        print("PROBE FAIL", out.stderr[-1500:]); sys.exit(1)
    return json.loads(out.stdout)

sw = words(stock, "stock")
fwc = words(fw, "trio")
changed = [i for i in range(256) if sw[i]["words"] != fwc[i]["words"]]
rerouted = [i for i in range(256) if sw[i]["pointers"] != fwc[i]["pointers"]]
print("changed modes:", changed)
print("rerouted modes:", rerouted)

# Inline curve generation (pure Python, no numpy) to run under WSL.
LOOK_PARAMS = {
    "gold200": (1.16, -3, 5), "portra160": (0.90, -1, 2), "velvia50": (1.42, 0, 1),
    "classicchrome": (0.82, 1, -1), "ektar100": (1.30, 0, 0), "bleach": (0.55, 0, 0),
    "moriyama_bw": (0.0, 0, 0), "trix_bw": (0.0, 0, 0),
}
def clamp(v, lo=0, hi=255): return max(lo, min(hi, v))
def axis_knots(scale, shift):
    if scale <= 0: return [clamp(128 + shift)] * 5
    ideal = [clamp(128 + shift + scale * (x - 128)) for x in range(256)]
    xs = [0, 64, 128, 192, 255]
    knots = [clamp(round(128 + shift + scale * (x - 128))) for x in xs]
    def interp(ks, v):
        for i in range(4):
            if v <= xs[i+1]:
                f = (v - xs[i]) / (xs[i+1] - xs[i])
                return ks[i] + f * (ks[i+1] - ks[i])
        return ks[4]
    def max_err(ks): return max(abs(interp(ks, v) - ideal[v]) for v in range(256))
    best = max_err(knots)
    for _ in range(60):
        improved = False
        for idx in (0, 1, 3, 4):
            for d in (-4, -2, -1, 1, 2, 4):
                trial = list(knots); trial[idx] = clamp(trial[idx] + d)
                e = max_err(trial)
                if e < best - 1e-9: knots, best, improved = trial, e, True
        if not improved: break
    return knots
def build_table(knots):
    y0, y64, y128, y192, y255 = knots
    x = bytes([0]*4 + [64, 128, 192] + [255]*9)
    y = bytes([y0]*4 + [y64, y128, y192] + [y255]*9)
    s0 = clamp(round((y64-y0)/64*128)); s1 = clamp(round((y128-y64)/64*128))
    s2 = clamp(round((y192-y128)/64*128)); s3 = clamp(round((y255-y192)/63*128))
    slope = bytes([0]*4 + [s0, s1, s2, s3] + [0]*9)
    return x + y + slope
slot_photo = {"I": 73, "II": 106, "III": 108}
slot_shared = {"I": 82, "II": 107, "III": 109}
ok = True
for slot, key in report["looks"].items():
    if not key:
        continue
    scale, cbs, crs = LOOK_PARAMS[key]
    cb = build_table(axis_knots(scale, cbs))
    cr = build_table(axis_knots(scale, crs))
    expect = pack_from_hex(cb.hex()) + pack_from_hex(cr.hex())
    pm = slot_photo[slot]
    match = fwc[pm]["words"] == expect
    print(f"slot {slot} ({key}) mode {pm} words match: {match}")
    ok &= match
    sm = slot_shared[slot]
    neutral = fwc[sm]["words"] == sw[69]["words"] and fwc[sm]["pointers"] == sw[69]["pointers"]
    print(f"slot {slot} shared mode {sm} stays factory-neutral: {neutral}")
    ok &= neutral

expected_changed = sorted(slot_photo[s] for s, k in report["looks"].items() if k)
expected_rerouted = sorted(slot_shared[s] for s, k in report["looks"].items() if k)
print("changed == expected photo modes:", changed == expected_changed)
print("rerouted == expected shared modes:", rerouted == expected_rerouted)
ok &= changed == expected_changed and rerouted == expected_rerouted
print("VERIFY", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
