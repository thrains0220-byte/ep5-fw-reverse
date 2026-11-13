"""Verify neutral trio: chroma changes only 73/106/108, shared 82/107/109 factory.
Also confirms the pinhole effect pointer is zeroed (neutralization)."""
import json, struct, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from external.oly_fw_analysis.tools import oly_container

fw = ROOT / "build/film-neutral-trio/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
runner = ROOT / "build/chroma-dump/ep5-contract-probe"
build = ROOT / "build" / "neutral-verify"
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

# Check shared modes keep factory identity
shared_ok = all(fwc[m]["words"] == sw[69]["words"] and fwc[m]["pointers"] == sw[69]["pointers"]
                for m in (82, 107, 109))
print("shared modes factory identity:", shared_ok)

# Check neutralization: pinhole effect pointer zeroed in firmware
fw_payload = oly_container.parse(fw.read_bytes())[0].payload
B = 0x7e101020
ptr_offs = [0x7e40b639 - B, 0x7e40b87a - B]
neutralized = all(struct.unpack_from("<I", fw_payload, off)[0] == 0 for off in ptr_offs)
print("pinhole effect pointer zeroed:", neutralized)

# All other modes unchanged
others_words = [i for i in range(256) if i not in (73, 106, 108) and sw[i]["words"] != fwc[i]["words"]]
others_ptrs = [i for i in range(256) if i not in (82, 107, 109) and sw[i]["pointers"] != fwc[i]["pointers"]]
print("other modes changed words (must be empty):", others_words)
print("other modes changed pointers (must be empty):", others_ptrs)

ok = (changed == [73, 106, 108] and rerouted == [82, 107, 109]
      and shared_ok and neutralized and not others_words and not others_ptrs)
print("VERIFY", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
