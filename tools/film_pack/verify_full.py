"""Verify FULL 7-slot film firmware writer isolation + neutralization + labels.

Only the 7 photo modes may change chroma words; the 7 rerouted shared modes must
become factory-neutral (mode 72 anchor words); every other mode stays factory.
Also confirms all 13 effect MOV immediates are zeroed and menu labels renamed.
"""
import json, struct, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from external.oly_fw_analysis.tools import oly_container

fw = ROOT / "build/film-full-7/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
runner = ROOT / "build/chroma-dump/ep5-contract-probe"
build = ROOT / "build" / "full-verify"
build.mkdir(exist_ok=True)

PHOTO = [69, 73, 106, 108, 86, 91, 153]
SHARED = [78, 82, 107, 109, 88, 93, 154]
NEUTRAL_ANCHOR = 72  # factory identity, gate=1 unreachable
EFFECT_OFFSETS = [
    0x7e40b810, 0x7e40b639, 0x7e40b87a, 0x7e40b679, 0x7e40b651,
    0x7e40b661, 0x7e40b682, 0x7e40b641, 0x7e40b649, 0x7e40b659,
    0x7e40b7e1, 0x7e40b669, 0x7e40b671,
]
# (offset, expected new label prefix)
LABELS = [
    (0x2ce1f8, "人像柔暖"), (0x2ce202, "胶片色彩"), (0x2ce19c, "风景鲜艳"),
    (0x2ce1ea, "电影色调"), (0x2ce18e, "森山黑白"),
    (0x2db40a, "人像柔暖"), (0x2db414, "膠片色彩"), (0x2db3a8, "風景鮮豔"),
    (0x2db3fc, "電影色調"), (0x2db39a, "森山黑白"),
]

def words(path, tag):
    main = build / f"{tag}.main"
    main.write_bytes(oly_container.parse(path.read_bytes())[0].payload)
    out = subprocess.run([str(runner), str(main), "chroma"], capture_output=True, text=True, timeout=60)
    if out.returncode:
        print("PROBE FAIL", out.stderr[-1500:]); sys.exit(1)
    return json.loads(out.stdout)

sw = words(stock, "stock")
fwc = words(fw, "full")
changed = [i for i in range(256) if sw[i]["words"] != fwc[i]["words"]]
rerouted = [i for i in range(256) if sw[i]["pointers"] != fwc[i]["pointers"]]
print("changed modes:", changed)
print("rerouted modes:", rerouted)

shared_ok = all(fwc[m]["words"] == sw[NEUTRAL_ANCHOR]["words"] for m in SHARED)
shared_ptrs_ok = all(fwc[m]["pointers"] == sw[NEUTRAL_ANCHOR]["pointers"] for m in SHARED)
others_words = [i for i in range(256) if i not in PHOTO and sw[i]["words"] != fwc[i]["words"]]
others_ptrs = [i for i in range(256) if i not in SHARED and sw[i]["pointers"] != fwc[i]["pointers"]]
print("shared factory-neutral:", shared_ok)
print("shared pointers -> neutral anchor:", shared_ptrs_ok)
print("other modes changed words (must be empty):", others_words)
print("other modes changed pointers (must be empty):", others_ptrs)

fw_payload = oly_container.parse(fw.read_bytes())[0].payload
B = 0x7e101020
neutralized = all(struct.unpack_from("<I", fw_payload, a - B)[0] == 0 for a in EFFECT_OFFSETS)
print("all effect pointers zeroed:", neutralized)

# Each photo mode's words must differ from factory (curve actually installed)
photo_changed = all(fwc[m]["words"] != sw[m]["words"] for m in PHOTO)
print("all 7 photo curves installed:", photo_changed)

# Menu labels
blocks = oly_container.parse(fw.read_bytes())
lang = blocks[1].payload
label_ok = True
for off, want in LABELS:
    raw = lang[off:off+14]
    text = raw.decode("utf-16-le").split("\0")[0]
    good = text.startswith(want)
    label_ok &= good
    print(f"  label @{off:#x}: {text!r} {'OK' if good else 'FAIL'}")

ok = (sorted(changed) == sorted(PHOTO) and sorted(rerouted) == sorted(SHARED)
      and shared_ok and shared_ptrs_ok and neutralized and photo_changed
      and not others_words and not others_ptrs and label_ok)
print("WRITER VERIFY", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
