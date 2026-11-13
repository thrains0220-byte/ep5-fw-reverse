"""Full capture-route verification for the 8-slot film firmware.

For each reachable photo slot, run the generalized route probe across movie
states 7/8/9 and confirm: correct packet mode, full-size allocation, JPEG
dispatch, RAW->YC converter, no effect function, and driver words that differ
from factory (curve installed). Shared/movie modes must keep factory words.
"""
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from tools.native_probe import build_probe
from external.oly_fw_analysis.tools import oly_container

fw = ROOT / "build/film-full-7/DCOLYMP/E1089999.BIN"
stock = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"

# (REC setting, variant, expected photo mode, look key, expected alloc calls)
# Composite (153) is a multi-frame blend: factory allocates 2 full-size buffers.
SLOTS = [
    (101, 1, 69, "portra400_hq", 1),    # soft focus
    (105, 1, 73, "velvia50_hq", 1),     # pinhole I
    (105, 2, 106, "classicchrome_hq", 1),# pinhole II
    (105, 3, 108, "gold200_hq", 1),     # pinhole III
    (106, 1, 86, "ektar100_hq", 1),     # diorama
    (108, 1, 91, "cinestill800t_hq", 1),# gentle sepia
    (118, 1, 153, "moriyama_bw_hq", 2), # composite / cross process (2-frame blend)
]

with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
    d = Path(tmp)
    probe = build_probe(ROOT / "tools/ep5_full_route_probe.c", d)
    mains = {}
    for tag, path in (("stock", stock), ("full", fw)):
        m = d / f"{tag}.main"
        m.write_bytes(oly_container.parse(path.read_bytes())[0].payload)
        mains[tag] = m
    ok = True
    for rec, variant, mode, key, nalloc in SLOTS:
        # factory words for this slot
        run = subprocess.run([str(probe), str(mains["stock"]), str(variant), "200", "7", str(rec)],
                             capture_output=True, text=True, timeout=30)
        if run.returncode:
            print(f"STOCK FAIL rec{rec} v{variant}", run.stderr[-600:]); ok = False; continue
        stock_wh = hashlib.sha256(bytes.fromhex(json.loads(run.stdout)["words_hex"])).hexdigest()
        for ms in (7, 8, 9):
            run = subprocess.run([str(probe), str(mains["full"]), str(variant), "200", str(ms), str(rec)],
                                 capture_output=True, text=True, timeout=30)
            if run.returncode:
                print(f"FULL FAIL rec{rec} v{variant} ms{ms}", run.stderr[-600:]); ok = False; continue
            c = json.loads(run.stdout)
            checks = {
                "packet_mode": c["packet_mode"] == mode,
                "gate": c["gate"] == 0,
                "alloc": c["allocation_calls"] == nalloc and c["allocation_bytes"] == 4608*3456*2,
                "jpeg": c["jpeg_target"] == 0x7e3f4884,
                "converter": c["converter"] == 0x7e40cbb1,
                "filter_zero": c["filter"] == 0,
                "geometry": c["codec"]["geometry"] == [4608, 3456, 4608, 3456],
                "driver_mode": c["driver_mode"] == mode,
                "words_changed": hashlib.sha256(bytes.fromhex(c["words_hex"])).hexdigest() != stock_wh,
            }
            good = all(checks.values())
            ok &= good
            bad = [k for k, v in checks.items() if not v]
            print(f"rec{rec} v{variant} mode{mode} ({key}) ms{ms}: {'OK' if good else 'FAIL ' + str(bad)}")
    print("ROUTE VERIFY", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
