"""Route probe for HQ neutral trio (same structure, different curve bytes)."""
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from tools.native_probe import build_probe
from external.oly_fw_analysis.tools import oly_container

fw = ROOT / "build/film-neutral-trio-hq/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"

with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
    d = Path(tmp)
    probe = build_probe(ROOT / "tools/ep5_film_route_probe.c", d)
    m = d / "hq.main"
    m.write_bytes(oly_container.parse(fw.read_bytes())[0].payload)
    ok = True
    for variant in (1, 2, 3):
        for ms in (7, 8, 9):
            run = subprocess.run([str(probe), str(m), str(variant), "200", str(ms)],
                                 capture_output=True, text=True, timeout=20)
            if run.returncode:
                print(f"FAIL v{variant} ms{ms}", run.stderr[-400:]); ok = False; continue
            c = json.loads(run.stdout)
            good = (c["packet_mode"] == {1:73,2:106,3:108}[variant]
                    and c["allocation_bytes"] == 4608*3456*2
                    and c["filter"] == 0
                    and c["converter"] == 0x7e40cbb1
                    and c["codec"]["geometry"] == [4608, 3456, 4608, 3456])
            ok &= good
            if not good:
                print(f"  v{variant} ms{ms} FAIL")
    print("HQ ROUTE VERIFY", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
