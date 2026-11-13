"""Build neutralized trio with HIGH-QUALITY 9-knot curves (non-linear saturation).
Same mechanism as build_neutral_trio but uses native_film_curves_hq."""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.film_update import build_update
from tools.inspect_ep5 import CPU_BASE, check_stock
from tools.native_film_curves_hq import HQ_LOOKS, build_hq_table
from tools.build_native_film_trio import SLOTS, NEUTRAL_CASE, _IDENTITY, SIZE, CARD_FILE

PINHOLE_PTR_OFFSETS = [0x7e40b639 - CPU_BASE, 0x7e40b87a - CPU_BASE]
PINHOLE_PTR_VALUE = 0x7e40115c

def look_by_key(key):
    for l in HQ_LOOKS:
        if l.key == key:
            return l
    raise ValueError(f"unknown HQ look {key!r}; choose from {[l.key for l in HQ_LOOKS]}")

def build(stock, looks):
    check_stock(stock)
    from external.oly_fw_analysis.tools import oly_container
    main_payload = oly_container.parse(stock)[0].payload
    edits = []
    for off in PINHOLE_PTR_OFFSETS:
        old = struct.unpack_from("<I", main_payload, off)[0]
        assert old == PINHOLE_PTR_VALUE
        edits.append((off, struct.pack("<I", old), struct.pack("<I", 0)))
    for slot, key in looks.items():
        if not key:
            continue
        s = SLOTS[slot]
        look = look_by_key(key)
        cb = build_hq_table(look.cb_points)
        cr = build_hq_table(look.cr_points)
        edits.append((s["pair"] - CPU_BASE, _IDENTITY * 2, cb + cr))
        jt_off = s["jt"] - CPU_BASE
        edits.append((jt_off, main_payload[jt_off:jt_off+4], struct.pack("<I", NEUTRAL_CASE)))
        for off, old, new in s["cmio"]:
            edits.append((off - CPU_BASE, struct.pack("<I", old), struct.pack("<I", new)))
    return build_update(stock, edits, language_edits=[])

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--i", required=True)
    p.add_argument("--ii", required=True)
    p.add_argument("--iii", required=True)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    if args.out.exists():
        p.exit(1, f"Output already exists: {args.out}\n")
    looks = {"I": args.i, "II": args.ii, "III": args.iii}
    stock = args.stock.read_bytes()
    fw = build(stock, looks)
    assert len(fw) == SIZE
    digest = hashlib.sha256(fw).hexdigest()
    args.out.mkdir(parents=True)
    card = args.out / CARD_FILE
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_bytes(fw)
    (args.out / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
    (args.out / "trio-report.json").write_text(json.dumps(
        {"looks": looks, "firmware_sha256": digest, "neutralized": True,
         "curve_quality": "9-knon-linear", "status": "candidate-pending-native-verification"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"built HQ neutral trio {looks}: {digest}")

if __name__ == "__main__":
    main()
