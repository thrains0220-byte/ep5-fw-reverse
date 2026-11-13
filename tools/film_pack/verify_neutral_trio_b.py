"""Verify neutral trio B (portra/velvia/moriyama): same checks as trio A."""
import json, struct, subprocess, sys, hashlib, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from external.oly_fw_analysis.tools import oly_container
from tools.native_probe import build_probe

fw = ROOT / "build/film-neutral-trio-b/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
report = json.loads((ROOT / "build/film-neutral-trio-b/trio-report.json").read_text(encoding="utf-8"))
runner = ROOT / "build/chroma-dump/ep5-contract-probe"
build = ROOT / "build" / "neutral-verify-b"
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
print("shared factory:", shared_ok, "neutralized:", neutralized)
ok = changed == [73, 106, 108] and rerouted == [82, 107, 109] and shared_ok and neutralized
print("WRITER VERIFY", "PASS" if ok else "FAIL")
if not ok:
    sys.exit(1)

# Route probe
with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
    d = Path(tmp)
    probe = build_probe(ROOT / "tools/ep5_film_route_probe.c", d)
    mains = {}
    for tag, path in (("stock", stock), ("neutral", fw)):
        m = d / f"{tag}.main"
        m.write_bytes(oly_container.parse(path.read_bytes())[0].payload)
        mains[tag] = m
    mode_of_variant = {1: 73, 2: 106, 3: 108}
    route_ok = True
    for variant in (1, 2, 3):
        for ms in (7, 8, 9):
            run = subprocess.run([str(probe), str(mains["neutral"]), str(variant), "200", str(ms)],
                                 capture_output=True, text=True, timeout=20)
            if run.returncode:
                print(f"ROUTE FAIL v{variant} ms{ms}", run.stderr[-400:]); route_ok = False; continue
            c = json.loads(run.stdout)
            good = (c["packet_mode"] == mode_of_variant[variant]
                    and c["allocation_bytes"] == 4608*3456*2
                    and c["filter"] == 0
                    and c["converter"] == 0x7e40cbb1
                    and c["codec"]["geometry"] == [4608, 3456, 4608, 3456])
            route_ok &= good
            if not good:
                print(f"  v{variant} ms{ms} FAIL: filter={c['filter']} mode={c['packet_mode']}")
    print("ROUTE VERIFY", "PASS" if route_ok else "FAIL")
    sys.exit(0 if route_ok else 1)
