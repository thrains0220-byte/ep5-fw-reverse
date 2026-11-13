"""Verify final HQ firmware: writer + route + menu label."""
import json, struct, subprocess, sys, hashlib, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from external.oly_fw_analysis.tools import oly_container
from tools.native_probe import build_probe

fw = ROOT / "build/film-final-hq/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
runner = ROOT / "build/chroma-dump/ep5-contract-probe"
build = ROOT / "build" / "final-verify"
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
shared_ok = all(fwc[m]["words"] == sw[69]["words"] for m in (82, 107, 109))
fw_payload = oly_container.parse(fw.read_bytes())[0].payload
B = 0x7e101020
neutralized = all(struct.unpack_from("<I", fw_payload, off)[0] == 0 for off in (0x7e40b639-B, 0x7e40b87a-B))
others = [i for i in range(256) if i not in (73,106,108) and sw[i]["words"] != fwc[i]["words"]]
print("shared factory:", shared_ok, "neutralized:", neutralized, "others:", others)
ok = changed == [73,106,108] and rerouted == [82,107,109] and shared_ok and neutralized and not others

# Verify menu label
label_off = 0x2ce202
# The language block is separate; check via the full firmware parse
blocks = oly_container.parse(fw.read_bytes())
lang_payload = blocks[1].payload if len(blocks) > 1 else None
if lang_payload:
    raw = lang_payload[label_off:label_off+14]
    text = raw.decode("utf-16-le").split("\0")[0]
    print(f"menu label: {repr(text)}")
    ok &= "胶片色彩" in text

print("WRITER VERIFY", "PASS" if ok else "FAIL")
if not ok:
    sys.exit(1)

# Route probe
with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
    d = Path(tmp)
    probe = build_probe(ROOT / "tools/ep5_film_route_probe.c", d)
    m = d / "final.main"
    m.write_bytes(fw_payload)
    route_ok = True
    for variant in (1, 2, 3):
        for ms in (7, 8, 9):
            run = subprocess.run([str(probe), str(m), str(variant), "200", str(ms)],
                                 capture_output=True, text=True, timeout=20)
            if run.returncode:
                print(f"ROUTE FAIL v{variant} ms{ms}"); route_ok = False; continue
            c = json.loads(run.stdout)
            good = (c["packet_mode"] == {1:73,2:106,3:108}[variant]
                    and c["allocation_bytes"] == 4608*3456*2
                    and c["filter"] == 0
                    and c["converter"] == 0x7e40cbb1
                    and c["codec"]["geometry"] == [4608, 3456, 4608, 3456])
            route_ok &= good
    print("ROUTE VERIFY", "PASS" if route_ok else "FAIL")
    sys.exit(0 if route_ok else 1)
