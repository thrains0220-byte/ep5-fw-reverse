"""Verify HQ neutral trio: 9-knot curves accepted by hardware writer."""
import json, struct, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from external.oly_fw_analysis.tools import oly_container

fw = ROOT / "build/film-neutral-trio-hq/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
runner = ROOT / "build/chroma-dump/ep5-contract-probe"
build = ROOT / "build" / "hq-verify"
build.mkdir(exist_ok=True)

def words(path):
    main = build / (path.parent.name + ".main")
    main.write_bytes(oly_container.parse(path.read_bytes())[0].payload)
    out = subprocess.run([str(runner), str(main), "chroma"], capture_output=True, text=True, timeout=30)
    if out.returncode:
        print("PROBE FAIL", out.stderr[-1500:]); sys.exit(1)
    return json.loads(out.stdout)

sw = words(stock)
fwc = words(fw)
changed = [i for i in range(256) if sw[i]["words"] != fwc[i]["words"]]
rerouted = [i for i in range(256) if sw[i]["pointers"] != fwc[i]["pointers"]]
print("changed modes:", changed)
print("rerouted modes:", rerouted)

# Verify the packed words match our generated tables
sys.path.insert(0, str(ROOT / "tools"))
from native_film_curves_hq import HQ_LOOKS, build_hq_table, pack_axis
report = json.loads((ROOT / "build/film-neutral-trio-hq/trio-report.json").read_text())
mode_of_slot = {"I": 73, "II": 106, "III": 108}
all_match = True
for slot, key in report["looks"].items():
    look = next(l for l in HQ_LOOKS if l.key == key)
    cb = build_hq_table(look.cb_points)
    cr = build_hq_table(look.cr_points)
    expect = pack_axis(cb) + pack_axis(cr)
    got = fwc[mode_of_slot[slot]]["words"]
    match = got == expect
    all_match &= match
    print(f"  {slot}({key}) mode{mode_of_slot[slot]} words match: {match}")
    if not match:
        for i in range(34):
            if got[i] != expect[i]:
                print(f"    word[{i}] got {got[i]:06x} want {expect[i]:06x}")

shared_ok = all(fwc[m]["words"] == sw[69]["words"] for m in (82, 107, 109))
fw_payload = oly_container.parse(fw.read_bytes())[0].payload
B = 0x7e101020
neutralized = all(struct.unpack_from("<I", fw_payload, off)[0] == 0 for off in (0x7e40b639-B, 0x7e40b87a-B))
others = [i for i in range(256) if i not in (73,106,108) and sw[i]["words"] != fwc[i]["words"]]
print("shared factory:", shared_ok, "neutralized:", neutralized, "others changed:", others)
ok = changed == [73,106,108] and rerouted == [82,107,109] and all_match and shared_ok and neutralized and not others
print("HQ VERIFY", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
