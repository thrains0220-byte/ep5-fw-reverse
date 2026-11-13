"""Build a D-branch diagnostic firmware: cave hooks installed but ALL disabled.

The module is present in the code cave and hooks are patched, but ep5_control
is all zeros (tag=0, enabled=0). Every hook entry checks the tag first and
returns immediately. No pixel writes, no ART neutralization, no SD loading.
The camera boots and shoots exactly as stock.

Purpose: verify that the cave region is loaded at boot, hooks don't crash,
and the camera remains fully functional. After confirming boot+shoot, the
next step enables mode 3 with a real SD card to test the full LUT chain.

SAFETY: hardware-diagnostic. No functional pixel modification is possible.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.cave_entry import build_payload, MAIN_SHA256, CAVE, BASE, HOOK, WAIT_HOOK, RELEASE_HOOK, PARAM_HOOK
from tools.film_update import build_update
from tools.inspect_ep5 import CPU_BASE, check_stock

SIZE = 44_826_624
CARD_FILE = "DCOLYMP/E1089999.BIN"

def build_diagnostic(stock_path: Path, out: Path):
    stock = stock_path.read_bytes()
    check_stock(stock)
    from external.oly_fw_analysis.tools import oly_container
    main_payload = oly_container.parse(stock)[0].payload
    
    # Build the cave module (same code, but control will be zeroed)
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
        module_dir = Path(tmp) / "module"
        manifest = build_payload(ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin", module_dir)
        payload = (module_dir / "film.bin").read_bytes()
    
    # Zero the control block inside the payload before installing
    ctrl_off = manifest["control_offset"]
    payload_mut = bytearray(payload)
    payload_mut[ctrl_off:ctrl_off+28] = bytes(28)
    payload = bytes(payload_mut)
    
    # Install module into cave region (single edit, no overlap)
    edits = [(CAVE - BASE, bytes([0xFF]) * len(payload), payload)]
    
    # Patch hooks (same as functional, but control=0 means they all return immediately)
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
        "firmware_sha256": digest,
        "module_bytes": len(payload),
        "control": "all-zero (disabled)",
        "pixel_writes": False,
        "art_neutralization": False,
        "sd_loading": False,
        "purpose": "Verify cave boot residency and hook safety; camera shoots stock.",
        "manifest": manifest,
    }
    (out / "diagnostic-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"built diagnostic: {digest}")
    print(f"  module: {len(payload)} bytes, control: ALL ZERO (disabled)")
    print(f"  no pixel writes, no neutralization, no SD loading")
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
