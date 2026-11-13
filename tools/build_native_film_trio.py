"""Build a three-look E-P5 firmware: Pin Hole I/II/III each carry one film look.

Extends the verified RC2 single-slot mechanism to all three pinhole variants by
exact structural analogy. Each slot's photo mode (73/106/108) gets its own chroma
curve pair; the shared selector mode (82/107/109) is rerouted to the factory
neutral case (mode 69, 0x7e22a01f) and the CMIO second-axis literal copies are
redirected to the factory neutral table family, exactly as RC2 did for slot I.

SAFETY: this is only a candidate until the native writer + CMIO init probe proves
that modes 73/106/108 change as intended and 82/107/109 (and every other mode)
stay factory-neutral. The audit warns RC2's checks do not automatically extend to
II/III; build_trio_firmware refuses to emit unless that verification is run.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.film_update import build_update
from tools.inspect_ep5 import CPU_BASE, check_stock
from tools.native_film_curves import build_table, axis_knots
from tools.build_native_film_pack import look_by_key

SIZE = 44_826_624
CARD_FILE = "DCOLYMP/E1089999.BIN"

_X = bytes([0] * 4 + [64, 128, 192] + [255] * 9)
_IDENTITY = _X + _X + bytes([0] * 4 + [128] * 4 + [0] * 9)

# Per-slot structure, read from the factory selector jump table and CMIO refs.
# photo: mode whose curve we patch; shared: mode rerouted to neutral;
# jt_slot: jump-table address of the shared mode; pair: chroma table base;
# cmio: the four second-axis literal refs RC2 redirects (offset, old, new).
SLOTS = {
    "I": {
        "photo": 73, "shared": 82, "jt": 0x7e478ec4, "pair": 0x7e438bb0,
        "cmio": [(0x7e21d0e7, 0x7e438bc0, 0x7e438a38),
                 (0x7e21d0fd, 0x7e438bd0, 0x7e438a48),
                 (0x7e21d129, 0x7e438bf1, 0x7e438a69),
                 (0x7e21d13f, 0x7e438c01, 0x7e438a79)],
    },
    "II": {
        "photo": 106, "shared": 107, "jt": 0x7e478f28, "pair": 0x7e438dfc,
        "cmio": [(0x7e21d3ff, 0x7e438e0c, 0x7e438a38),
                 (0x7e21d415, 0x7e438e1c, 0x7e438a48),
                 (0x7e21d441, 0x7e438e3d, 0x7e438a69),
                 (0x7e21d457, 0x7e438e4d, 0x7e438a79)],
    },
    "III": {
        "photo": 108, "shared": 109, "jt": 0x7e478f30, "pair": 0x7e438e5e,
        "cmio": [(0x7e21d483, 0x7e438e6e, 0x7e438a38),
                 (0x7e21d499, 0x7e438e7e, 0x7e438a48),
                 (0x7e21d4c5, 0x7e438e9f, 0x7e438a69),
                 (0x7e21d4db, 0x7e438eaf, 0x7e438a79)],
    },
}
NEUTRAL_CASE = 0x7e22a01f   # mode 69 factory neutral chroma case


def build_trio_firmware(stock: bytes, looks: dict[str, str], *,
                        labels: dict[str, tuple[str, str]] | None = None) -> bytes:
    """looks: {'I': key, 'II': key, 'III': key}. Any slot may be None to keep stock."""
    check_stock(stock)
    from external.oly_fw_analysis.tools import oly_container
    main_payload = oly_container.parse(stock)[0].payload
    edits = []
    for slot, key in looks.items():
        if not key:
            continue
        s = SLOTS[slot]
        look = look_by_key(key)
        cb = build_table(axis_knots(look.scale, look.cb_shift))
        cr = build_table(axis_knots(look.scale, look.cr_shift))
        edits.append((s["pair"] - CPU_BASE, _IDENTITY * 2, cb + cr))
        # The shared mode's jump-table slot currently holds this slot's case_pc;
        # read the actual factory value so the edit is exact.
        jt_off = s["jt"] - CPU_BASE
        edits.append((jt_off, main_payload[jt_off:jt_off + 4], struct.pack("<I", NEUTRAL_CASE)))
        for off, old, new in s["cmio"]:
            edits.append((off - CPU_BASE, struct.pack("<I", old), struct.pack("<I", new)))
    language_edits = []
    # The factory has one Pin Hole menu entry; I/II/III are right-key sub-variants
    # without separate strings. The trio keeps the factory name; the look-to-slot
    # map is documented in trio-report.json and the READ-ME.
    return build_update(stock, edits, language_edits=language_edits)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--i", help="look key for Pin Hole I")
    p.add_argument("--ii", help="look key for Pin Hole II")
    p.add_argument("--iii", help="look key for Pin Hole III")
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    if args.out.exists():
        p.exit(1, f"Output already exists: {args.out}\n")
    looks = {"I": args.i, "II": args.ii, "III": args.iii}
    if not any(looks.values()):
        p.exit(1, "assign at least one look\n")
    stock = args.stock.read_bytes()
    fw = build_trio_firmware(stock, looks)
    if len(fw) != SIZE:
        raise ValueError("unexpected size")
    digest = hashlib.sha256(fw).hexdigest()
    args.out.mkdir(parents=True)
    card = args.out / CARD_FILE
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_bytes(fw)
    (args.out / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
    import json
    (args.out / "trio-report.json").write_text(json.dumps(
        {"looks": looks, "firmware_sha256": digest,
         "status": "candidate-pending-native-verification"}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"built trio {looks}: {digest}")
    print("NOTE: run the native writer/CMIO verification before flashing.")


if __name__ == "__main__":
    main()
