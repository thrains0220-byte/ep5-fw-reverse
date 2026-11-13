"""Build a single-look E-P5 film firmware on the Gentle Sepia (浓郁色调) slot.

Reuses the hardware-verified RC2 chroma-curve mechanism, but on the gentle_sepia
ART slot (photo mode 91 / shared movie mode 93) instead of Pin Hole I. This slot
has NO vignette and NO blur — its only native effect is a warm sepia tint, so it
suits warm film looks (Gold 200 / Portra). The chroma table pair, jump-table slot
and CMIO literal copies are structurally identical to Pin Hole I (see
docs/NON_PINHOLE_CARRIERS.md), so the same isolation applies.

SAFETY: hardware-functional-candidate. The mechanism booted/shot/recovered on one
E-P5 as Pin Hole RC2; this gentle_sepia slot variant must pass the native writer +
route probes (91 changes, 93 and all other modes stay factory) before flashing,
and the sepia base tint means cool/high-saturation looks will be muddied.
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
from tools.inspect_ep5 import CPU_BASE, STOCK_SHA256, check_stock
from tools.native_film_curves import build_table, axis_knots, look_tables
from tools.build_native_film_pack import look_by_key, _fit_label

SIZE = 44_826_624
CARD_FILE = "DCOLYMP/E1089999.BIN"

_X = bytes([0] * 4 + [64, 128, 192] + [255] * 9)
_IDENTITY = _X + _X + bytes([0] * 4 + [128] * 4 + [0] * 9)

# gentle_sepia slot structure (read from factory jump table + CMIO refs).
PAIR = 0x7e438cd6
JT_SHARED = 0x7e478ef0  # jump-table slot for shared mode 93 (factory case 0x7e22a1fb)
NEUTRAL_CASE = 0x7e22a01f
# CMIO second-axis literal copies: (offset, factory old, neutral new).
CMIO = [
    (0x7e21d273, 0x7e438ce6, 0x7e438a38),
    (0x7e21d289, 0x7e438cf6, 0x7e438a48),
    (0x7e21d2b5, 0x7e438d17, 0x7e438a69),
    (0x7e21d2cb, 0x7e438d27, 0x7e438a79),
]


def build_gentle_firmware(stock: bytes, look, *, label_zh=None, label_zht=None) -> bytes:
    check_stock(stock)
    from external.oly_fw_analysis.tools import oly_container
    main_payload = oly_container.parse(stock)[0].payload
    cb = build_table(axis_knots(look.scale, look.cb_shift))
    cr = build_table(axis_knots(look.scale, look.cr_shift))
    edits = [(PAIR - CPU_BASE, _IDENTITY * 2, cb + cr)]
    jt_off = JT_SHARED - CPU_BASE
    edits.append((jt_off, main_payload[jt_off:jt_off + 4], struct.pack("<I", NEUTRAL_CASE)))
    for off, old, new in CMIO:
        edits.append((off - CPU_BASE, struct.pack("<I", old), struct.pack("<I", new)))
    # Gentle Sepia factory labels (6 UTF-16 units), icon @A03F@. Offsets read from
    # the factory language directory (build/art-full.json): zh-Hans 67/597,
    # zh-Hant 67/597. Traditional factory text is "濃化色調效果".
    zh = _fit_label(label_zh or look.name_zh)
    zht = _fit_label(label_zht or label_zh or look.name_zh)
    language_edits = []
    for offset, prefix, old, new in (
        (0x2ce1ea, "", "浓郁色调效果", zh),
        (0x2d082a, "@A03F@", "浓郁色调效果", zh),
        (0x2db3fc, "", "濃化色調效果", zht),
        (0x2dda72, "@A03F@", "濃化色調效果", zht),
    ):
        before = (prefix + old + "\0").encode("utf-16-le")
        after = (prefix + new + "\0").encode("utf-16-le")
        if len(before) != len(after):
            raise ValueError(f"label {new!r} byte length mismatch")
        language_edits.append((offset, before, after))
    return build_update(stock, edits, language_edits=language_edits)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--look", required=True)
    p.add_argument("--label-zh")
    p.add_argument("--label-zht")
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    if args.out.exists():
        p.exit(1, f"Output already exists: {args.out}\n")
    look = look_by_key(args.look)
    stock = args.stock.read_bytes()
    fw = build_gentle_firmware(stock, look, label_zh=args.label_zh, label_zht=args.label_zht)
    if len(fw) != SIZE:
        raise ValueError("unexpected size")
    digest = hashlib.sha256(fw).hexdigest()
    args.out.mkdir(parents=True)
    card = args.out / CARD_FILE
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_bytes(fw)
    (args.out / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
    report = look_tables(look)
    report.update(firmware_sha256=digest, stock_sha256=STOCK_SHA256,
                  slot="gentle_sepia (photo 91 / shared 93)",
                  mechanism="RC2-verified chroma-curve patch on gentle_sepia; no vignette; warm sepia base tint",
                  status="hardware-functional-candidate (run native writer+route probes before flashing)")
    (args.out / "look-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"built gentle_sepia {look.key}: {digest}")


if __name__ == "__main__":
    main()
