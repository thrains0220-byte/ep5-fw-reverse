"""Verify SAFE 7-slot firmware: chroma isolation + effects PRESERVED (non-zero).

This is the inverse of verify_full.py on the effect check: every effect MOV
immediate must still hold its factory function pointer (NOT zero), because
zeroing them caused ART black-screen on hardware.
"""
import json, struct, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from external.oly_fw_analysis.tools import oly_container

fw = ROOT / "build/film-safe-7/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
runner = ROOT / "build/chroma-dump/ep5-contract-probe"
build = ROOT / "build" / "safe-verify"
build.mkdir(exist_ok=True)

PHOTO = [69, 73, 106, 108, 86, 91, 153]
SHARED = [78, 82, 107, 109, 88, 93, 154]
NEUTRAL_ANCHOR = 72
# (offset, factory pointer value) — must remain UNCHANGED
EFFECT_PTRS = [
    (0x7e40b810, 0x7e4024d0),  # soft_focus
    (0x7e40b639, 0x7e40115c), (0x7e40b87a, 0x7e40115c),  # pinhole
    (0x7e40b679, 0x7e4052e2),  # gentle_sepia
    (0x7e40b651, 0x7e4055ba),  # dramatic_tone
    (0x7e40b661, 0x7e4067dd),  # artclearline
    (0x7e40b682, 0x7e4085ef),  # pastel_art
    (0x7e40b641, 0x7e4037d7),  # rough_mono
    (0x7e40b649, 0x7e404690),  # diorama
    (0x7e40b659, 0x7e3ff52f), (0x7e40b7e1, 0x7e3ff52f),  # star_light
    (0x7e40b669, 0x7e407f6e),  # mirror
    (0x7e40b671, 0x7e40811e),  # composite
]

def words(path, tag):
    main = build / f"{tag}.main"
    main.write_bytes(oly_container.parse(path.read_bytes())[0].payload)
    out = subprocess.run([str(runner), str(main), "chroma"], capture_output=True, text=True, timeout=60)
    if out.returncode:
        print("PROBE FAIL", out.stderr[-1500:]); sys.exit(1)
    return json.loads(out.stdout)

sw = words(stock, "stock")
fwc = words(fw, "safe")
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
effects_preserved = True
for addr, val in EFFECT_PTRS:
    got = struct.unpack_from("<I", fw_payload, addr - B)[0]
    if got != val:
        effects_preserved = False
        print(f"  EFFECT CHANGED @{addr:#x}: got {got:#x} want {val:#x}")
print("all factory effect pointers preserved:", effects_preserved)

photo_changed = all(fwc[m]["words"] != sw[m]["words"] for m in PHOTO)
print("all 7 photo curves installed:", photo_changed)

blocks = oly_container.parse(fw.read_bytes())
lang = blocks[1].payload
labels = json.loads((ROOT / "build/film-safe-7/labels.json").read_text(encoding="utf-8"))
label_ok = True
for item in labels:
    off = int(item["off"], 16)
    want = item["want"]
    text = lang[off:off+14].decode("utf-16-le").split("\0")[0]
    good = text.startswith(want)
    label_ok &= good
    print(f"  label @{off:#x}: {text!r} {'OK' if good else 'FAIL'}")

ok = (sorted(changed) == sorted(PHOTO) and sorted(rerouted) == sorted(SHARED)
      and shared_ok and shared_ptrs_ok and effects_preserved and photo_changed
      and not others_words and not others_ptrs and label_ok)
print("SAFE VERIFY", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
