"""Build a three-look E-P5 firmware with NEUTRALIZED pinhole (no vignette).

Extends the verified trio mechanism: in addition to patching chroma curves and
rerouting shared modes, this zeroes the pinhole effect function pointer in
art_set_filter so the list builder only queues RAW->YC. The result is three
clean film-color slots with NO vignette, NO blur, NO sepia — just the native
chroma curve applied to a neutral RAW development.

The neutralization is a 4-byte ROM constant change (MOV immediate -> 0), proven
by CPU probe to preserve packet modes 73/106/108 and leave all other filters
unchanged. Risk level: same as RC2 chroma-curve patch (data-only, no new code).

SAFETY: hardware-functional-candidate. Must pass native writer + route probes
before flashing. The route probe must confirm filter=0 (no effect function).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.film_update import build_update
from tools.inspect_ep5 import CPU_BASE, check_stock
from tools.native_film_curves import build_table, axis_knots
from tools.build_native_film_pack import look_by_key
from tools.build_native_film_trio import SLOTS, NEUTRAL_CASE, _IDENTITY, SIZE, CARD_FILE

# Pinhole effect function pointer locations in art_set_filter (MOV immediates).
# Zeroing these makes the list builder skip the pinhole effect for all variants.
PINHOLE_PTR_OFFSETS = [0x7e40b639 - CPU_BASE, 0x7e40b87a - CPU_BASE]
PINHOLE_PTR_VALUE = 0x7e40115c


def build_neutral_trio(stock: bytes, looks: dict[str, str], *,
                       labels: dict[str, tuple[str, str]] | None = None) -> bytes:
    """looks: {'I': key, 'II': key, 'III': key}. Any slot may be None to keep stock."""
    check_stock(stock)
    from external.oly_fw_analysis.tools import oly_container
    main_payload = oly_container.parse(stock)[0].payload
    edits = []

    # 1. Neutralize pinhole effect: zero the MOV immediate pointers.
    for off in PINHOLE_PTR_OFFSETS:
        old = struct.unpack_from("<I", main_payload, off)[0]
        if old != PINHOLE_PTR_VALUE:
            raise ValueError(f"unexpected pinhole ptr at {hex(CPU_BASE+off)}: {hex(old)}")
        edits.append((off, struct.pack("<I", old), struct.pack("<I", 0)))

    # 2. Per-slot chroma curves + shared mode reroute + CMIO (same as trio).
    for slot, key in looks.items():
        if not key:
            continue
        s = SLOTS[slot]
        look = look_by_key(key)
        cb = build_table(axis_knots(look.scale, look.cb_shift))
        cr = build_table(axis_knots(look.scale, look.cr_shift))
        edits.append((s["pair"] - CPU_BASE, _IDENTITY * 2, cb + cr))
        jt_off = s["jt"] - CPU_BASE
        edits.append((jt_off, main_payload[jt_off:jt_off + 4], struct.pack("<I", NEUTRAL_CASE)))
        for off, old, new in s["cmio"]:
            edits.append((off - CPU_BASE, struct.pack("<I", old), struct.pack("<I", new)))

    return build_update(stock, edits, language_edits=[])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--i", help="look key for Pin Hole I (neutralized)")
    p.add_argument("--ii", help="look key for Pin Hole II (neutralized)")
    p.add_argument("--iii", help="look key for Pin Hole III (neutralized)")
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    if args.out.exists():
        p.exit(1, f"Output already exists: {args.out}\n")
    looks = {"I": args.i, "II": args.ii, "III": args.iii}
    if not any(looks.values()):
        p.exit(1, "assign at least one look\n")
    stock = args.stock.read_bytes()
    fw = build_neutral_trio(stock, looks)
    if len(fw) != SIZE:
        raise ValueError("unexpected size")
    digest = hashlib.sha256(fw).hexdigest()
    args.out.mkdir(parents=True)
    card = args.out / CARD_FILE
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_bytes(fw)
    (args.out / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
    (args.out / "trio-report.json").write_text(json.dumps(
        {"looks": looks, "firmware_sha256": digest,
         "neutralized": True, "vignette": False,
         "status": "candidate-pending-native-verification"}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"built neutral trio {looks}: {digest}")
    print("NOTE: run native writer + route verification before flashing.")


if __name__ == "__main__":
    main()
