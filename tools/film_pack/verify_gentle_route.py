"""Full capture-route probe for the gentle_sepia film slot (REC 108 -> mode 91).
Confirms allocation, JPEG dispatch, converter/filter and driver words across movie
states 7/8/9. Pure Python; WSL with cc-built gentle route probe."""
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from tools.native_probe import build_probe
from external.oly_fw_analysis.tools import oly_container

key = sys.argv[1] if len(sys.argv) > 1 else "gold200"
fw = ROOT / f"build/film-gentle-{key}/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"

with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
    d = Path(tmp)
    probe = build_probe(ROOT / "tools/ep5_gentle_route_probe.c", d)
    mains = {}
    for tag, path in (("stock", stock), ("gentle", fw)):
        m = d / f"{tag}.main"
        m.write_bytes(oly_container.parse(path.read_bytes())[0].payload)
        mains[tag] = m
    ok = True
    # gentle_sepia has no I/II/III sub-variants; variant 1 is the canonical route.
    variant = 1
    run = subprocess.run([str(probe), str(mains["stock"]), str(variant), "200", "7"],
                         capture_output=True, text=True, timeout=20)
    if run.returncode:
        print("STOCK PROBE FAIL", run.stderr[-800:]); sys.exit(1)
    stock_words = hashlib.sha256(bytes.fromhex(json.loads(run.stdout)["words_hex"])).hexdigest()
    for movie_state in (7, 8, 9):
        run = subprocess.run([str(probe), str(mains["gentle"]), str(variant), "200", str(movie_state)],
                             capture_output=True, text=True, timeout=20)
        if run.returncode:
            print(f"GENTLE PROBE FAIL ms{movie_state}", run.stderr[-800:]); ok = False; continue
        c = json.loads(run.stdout)
        checks = {
            "packet_mode": c["packet_mode"] == 91,
            "alloc": c["allocation_calls"] == 1 and c["allocation_bytes"] == 4608*3456*2,
            "jpeg_target": c["jpeg_target"] == 0x7e3f4884,
            "converter": c["converter"] == 0x7e40cbb1,
            "filter": c["filter"] == 0x7e4052e2,
            "geometry": c["codec"]["geometry"] == [4608, 3456, 4608, 3456],
            "driver_mode": c["driver_mode"] == 91,
            "words_changed": hashlib.sha256(bytes.fromhex(c["words_hex"])).hexdigest() != stock_words,
        }
        good = all(checks.values())
        ok &= good
        print(f"gentle ms{movie_state}: {'OK' if good else 'FAIL'} "
              f"{[k for k,v in checks.items() if not v] if not good else ''}")
    print("ROUTE VERIFY", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
