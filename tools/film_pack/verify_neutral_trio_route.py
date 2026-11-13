"""Full capture-route probe for neutralized trio (no vignette).
Confirms: filter=0 (no effect), allocation full-size, JPEG dispatch, driver words.
Uses the existing pinhole route probe (REC 105) since modes are still 73/106/108."""
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from tools.native_probe import build_probe
from external.oly_fw_analysis.tools import oly_container

fw = ROOT / "build/film-neutral-trio/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
report = json.loads((ROOT / "build/film-neutral-trio/trio-report.json").read_text(encoding="utf-8"))

with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
    d = Path(tmp)
    probe = build_probe(ROOT / "tools/ep5_film_route_probe.c", d)
    mains = {}
    for tag, path in (("stock", stock), ("neutral", fw)):
        m = d / f"{tag}.main"
        m.write_bytes(oly_container.parse(path.read_bytes())[0].payload)
        mains[tag] = m
    slot_of_variant = {1: "I", 2: "II", 3: "III"}
    mode_of_variant = {1: 73, 2: 106, 3: 108}
    ok = True
    stock_words = {}
    for variant in (1, 2, 3):
        run = subprocess.run([str(probe), str(mains["stock"]), str(variant), "200", "7"],
                             capture_output=True, text=True, timeout=20)
        if run.returncode:
            print("STOCK PROBE FAIL", run.stderr[-800:]); sys.exit(1)
        stock_words[variant] = hashlib.sha256(bytes.fromhex(json.loads(run.stdout)["words_hex"])).hexdigest()
    for variant in (1, 2, 3):
        slot = slot_of_variant[variant]
        key = report["looks"].get(slot)
        for movie_state in (7, 8, 9):
            run = subprocess.run([str(probe), str(mains["neutral"]), str(variant), "200", str(movie_state)],
                                 capture_output=True, text=True, timeout=20)
            if run.returncode:
                print(f"NEUTRAL PROBE FAIL v{variant} ms{movie_state}", run.stderr[-800:]); ok = False; continue
            c = json.loads(run.stdout)
            checks = {
                "packet_mode": c["packet_mode"] == mode_of_variant[variant],
                "alloc": c["allocation_calls"] == 1 and c["allocation_bytes"] == 4608*3456*2,
                "jpeg_target": c["jpeg_target"] == 0x7e3f4884,
                "converter": c["converter"] == 0x7e40cbb1,
                # NEUTRALIZED: no effect function queued
                "filter_zero": c["filter"] == 0,
                "geometry": c["codec"]["geometry"] == [4608, 3456, 4608, 3456],
                "driver_mode": c["driver_mode"] == mode_of_variant[variant],
            }
            wh = hashlib.sha256(bytes.fromhex(c["words_hex"])).hexdigest()
            if key:
                checks["words_changed"] = wh != stock_words[variant]
            else:
                checks["words_stock"] = wh == stock_words[variant]
            good = all(checks.values())
            ok &= good
            print(f"v{variant}({slot}={key}) ms{movie_state}: {'OK' if good else 'FAIL'} "
                  f"{[k for k,v in checks.items() if not v] if not good else ''}")
    print("ROUTE VERIFY", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
