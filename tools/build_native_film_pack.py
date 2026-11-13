"""Build single-look E-P5 film firmware on the proven RC2 chroma-curve mechanism.

Each look occupies the factory Pin Hole I slot (photo mode 73) exactly as the
hardware-verified Soft Chrome RC2 did: two 49-byte native chroma curves are
patched, movie mode 82 is rerouted to a byte-identical factory identity table so
video keeps stock, and the shared CMIO copies are redirected. No new executable
code, no extra task, no luma change. The only differences from RC2 are the curve
bytes (from native_film_curves) and the ART menu label.

This is a hardware-functional candidate built on a mechanism that already booted,
shot full-size RAW+JPEG and recovered on one E-P5. It is NOT camera-verified for
these new curves; the chroma approximation error is reported per look.
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
from tools.inspect_ep5 import CPU_BASE, STOCK_SHA256, check_stock
from tools.native_film_curves import LOOKS, NativeLook, build_table, axis_knots, look_tables

SIZE = 44_826_624
CARD_FILE = "DCOLYMP/E1089999.BIN"

# Factory identity table pair (98 bytes) at the Pin Hole I chroma address.
_X = bytes([0] * 4 + [64, 128, 192] + [255] * 9)
_IDENTITY = _X + _X + bytes([0] * 4 + [128] * 4 + [0] * 9)


def look_by_key(key: str) -> NativeLook:
    for look in LOOKS:
        if look.key == key:
            return look
    raise ValueError(f"unknown look {key!r}; choose from {[l.key for l in LOOKS]}")


# The factory ART name occupies exactly six UTF-16 code units ("针孔相机效果").
# Labels are padded with full-width spaces to that width so the replacement is
# always byte-equal, preserving the language pack's entry count and pointers.
_LABEL_UNITS = 6


def _fit_label(text: str) -> str:
    if len(text) > _LABEL_UNITS:
        raise ValueError(f"label {text!r} exceeds {_LABEL_UNITS} UTF-16 units")
    return text + "\u3000" * (_LABEL_UNITS - len(text))


def build_look_firmware(stock: bytes, look: NativeLook, *, label_zh: str | None = None,
                        label_zht: str | None = None) -> bytes:
    """Patch the Pin Hole I chroma curves to `look`, keeping movie/CMIO stock."""
    check_stock(stock)
    cb = build_table(axis_knots(look.scale, look.cb_shift))
    cr = build_table(axis_knots(look.scale, look.cr_shift))
    # The factory pair is two identical 49-byte axes; the new pair is cb then cr.
    edits = [(0x7e438bb0 - CPU_BASE, _IDENTITY * 2, cb + cr)]
    # Movie mode 82 reroute + shared CMIO copies: identical to verified RC2.
    for address, old, new in (
        (0x7e478ec4, 0x7e22a12f, 0x7e22a01f),
        (0x7e21d0e7, 0x7e438bc0, 0x7e438a38),
        (0x7e21d0fd, 0x7e438bd0, 0x7e438a48),
        (0x7e21d129, 0x7e438bf1, 0x7e438a69),
        (0x7e21d13f, 0x7e438c01, 0x7e438a79),
    ):
        edits.append((address - CPU_BASE, struct.pack("<I", old), struct.pack("<I", new)))
    # ART menu label: equal-length UTF-16 replacement of the Pin Hole name.
    zh = _fit_label(label_zh or look.name_zh)
    zht = _fit_label(label_zht or label_zh or look.name_zh)
    language_edits = []
    for offset, prefix, old, new in (
        (0x2ce202, "", "针孔相机效果", zh),
        (0x2d08ae, "@A045@", "针孔相机效果", zh),
        (0x2db414, "", "針孔相機效果", zht),
        (0x2ddaf8, "@A045@", "針孔相機效果", zht),
    ):
        before = (prefix + old + "\0").encode("utf-16-le")
        after = (prefix + new + "\0").encode("utf-16-le")
        if len(before) != len(after):
            raise ValueError(f"label {new!r} byte length mismatch ({len(before)} vs {len(after)})")
        language_edits.append((offset, before, after))
    return build_update(stock, edits, language_edits=language_edits)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path, help="original OLY_E_108_1800_0000_0000.BIN")
    parser.add_argument("--look", required=True, help="look key, e.g. gold200")
    parser.add_argument("--label-zh", help="simplified ART label (equal byte length)")
    parser.add_argument("--label-zht", help="traditional ART label (equal byte length)")
    parser.add_argument("--out", required=True, type=Path, help="new local output directory")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.exit(1, f"Output already exists: {args.out}\n")
    look = look_by_key(args.look)
    stock = args.stock.read_bytes()
    firmware = build_look_firmware(stock, look, label_zh=args.label_zh, label_zht=args.label_zht)
    if len(firmware) != SIZE:
        raise ValueError("unexpected firmware size")
    digest = hashlib.sha256(firmware).hexdigest()
    args.out.mkdir(parents=True)
    card = args.out / CARD_FILE
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_bytes(firmware)
    (args.out / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
    import json
    report = look_tables(look)
    report["firmware_sha256"] = digest
    report["stock_sha256"] = STOCK_SHA256
    report["mechanism"] = "RC2-verified Pin Hole I chroma-curve patch; movie/CMIO rerouted to stock"
    report["status"] = "hardware-functional-candidate (mechanism verified on E-P5; these curves not yet camera-shot)"
    (args.out / "look-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"built {look.key}: {digest}")
    print(f"  chroma max err: {max(report['chroma_error']['cb_max'], report['chroma_error']['cr_max']):.1f}")
    if report["rgb_target_error"]:
        print(f"  rgb target mean err: {report['rgb_target_error']['mean_rgb8_error']:.1f}")


if __name__ == "__main__":
    main()
