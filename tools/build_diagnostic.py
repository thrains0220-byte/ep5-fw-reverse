"""Build an experimental enabled observe-only diagnostic package.

This script installs hooks and enables mode 4, which records request fields
and attempts SD writes from an unverified camera task context. The build omits
functional pixel modification, but is NOT verified safe or ready to flash.
It does not establish a safe route to enable mode 3. Offline model results
cannot prove camera boot, shooting, shutdown, storage, or recovery behavior.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.cave_entry import build_diag_payload, MAIN_SHA256, CAVE, BASE, HOOK, WAIT_HOOK, RELEASE_HOOK, PARAM_HOOK
from tools.film_update import build_update
from tools.inspect_ep5 import CPU_BASE, check_stock

SIZE = 44_826_624
CARD_FILE = "DCOLYMP/E1089999.BIN"

def build_diagnostic(stock_path: Path, out: Path):
    stock = stock_path.read_bytes()
    check_stock(stock)
    from external.oly_fw_analysis.tools import oly_container
    main_payload = oly_container.parse(stock)[0].payload
    
    # Build the compile-time observe-only diagnostic module. Pixel/LUT code is
    # absent from this ELF; control=4 enables only request observation/logging.
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
        module_dir = Path(tmp) / "module"
        manifest = build_diag_payload(ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin", module_dir)
        payload = (module_dir / "diag.bin").read_bytes()
    
    # Set enabled=4 inside the control block (tag + diagnostic mode).
    ctrl_off = manifest["control_offset"]
    payload_mut = bytearray(payload)
    struct.pack_into("<7I", payload_mut, ctrl_off, 0x43355045, 4, 0, 0, 0, 0, 0)
    payload = bytes(payload_mut)
    
    # Install module into cave region (single edit, no overlap)
    edits = [(CAVE - BASE, bytes([0xFF]) * len(payload), payload)]
    
    # Patch hooks; mode 4 executes diagnostic observation and may write a log.
    for patch_key in ("patch", "wait_patch", "release_patch", "param_patch"):
        p = manifest[patch_key]
        off = p["image_offset"]
        old = bytes.fromhex(p["old"].replace(" ", ""))
        new = bytes.fromhex(p["new"].replace(" ", ""))
        edits.append((off, old, new))
    
    fw = build_update(stock, edits, language_edits=[])
    assert len(fw) == SIZE
    digest = hashlib.sha256(fw).hexdigest()
    
    out.mkdir(parents=True, exist_ok=True)
    card = out / CARD_FILE
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_bytes(fw)
    (out / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
    report = {
        "type": "hardware-diagnostic",
        "ready_to_flash": False,
        "physical_camera_test": False,
        "risk": "Enabled hooks and SD log writes in an unverified camera task context; no claim of safe boot or recovery.",
        "firmware_sha256": digest,
        "module_bytes": len(payload),
        "control": "tag=EP5, enabled=4 (observe-only)",
        "pixel_writes": False,
        "art_neutralization": False,
        "sd_loading": False,
        "diagnostic_log": "EP5LUT/DIAG.LOG (128-byte records)",
        "purpose": "Capture real JPEG request/buffer contract while stock imaging runs.",
        "manifest": manifest,
    }
    (out / "diagnostic-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"built diagnostic: {digest}")
    print(f"  module: {len(payload)} bytes, control: tag=EP5 enabled=4")
    print(f"  no pixel writes, no neutralization, no LUT loading; logs EP5LUT/DIAG.LOG")
    return report

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    if args.out.exists():
        p.exit(1, f"Output already exists: {args.out}\n")
    build_diagnostic(args.stock, args.out)

if __name__ == "__main__":
    main()
