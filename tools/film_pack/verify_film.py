"""Verify a built film pack: only mode 73 chroma changes, movie 82 stays stock.
Pure Python (no numpy) so it runs under WSL. Reads the look params from the
build's look-report.json and regenerates the expected packed words inline."""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from external.oly_fw_analysis.tools import oly_container

key = sys.argv[1] if len(sys.argv) > 1 else "gold200"
fw = ROOT / f"build/film-{key}/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
report = json.loads((ROOT / f"build/film-{key}/look-report.json").read_text(encoding="utf-8"))
runner = ROOT / "build/chroma-dump/ep5-contract-probe"
build = ROOT / "build" / "film-verify"
build.mkdir(exist_ok=True)

def clamp(v, lo=0, hi=255):
    return max(lo, min(hi, v))

def pack_from_hex(h):
    t = bytes.fromhex(h)
    x, y, slope = t[0:16], t[16:32], t[32:49]
    return [ (x[i-1] if i>=1 else 0) | ((y[i-1] if i>=1 else 0)<<8) | (slope[i]<<16) for i in range(17) ]

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
expect = pack_from_hex(report["cb_table_hex"]) + pack_from_hex(report["cr_table_hex"])
got = fwc[73]["words"]
print("mode73 words match generated tables:", got == expect)
if got != expect:
    for i in range(34):
        if got[i] != expect[i]:
            print(f"  word[{i}] got {got[i]:06x} want {expect[i]:06x}")
print("movie82 rerouted to stock69 table:", fwc[82]["pointers"] == sw[69]["pointers"])
print("movie82 words == stock identity:", fwc[82]["words"] == sw[69]["words"])
ok = changed == [73] and got == expect and fwc[82]["pointers"] == sw[69]["pointers"]
print("VERIFY", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
