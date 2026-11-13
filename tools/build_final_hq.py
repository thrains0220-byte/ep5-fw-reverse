"""Build the FINAL HQ neutral trio with proper camera menu labels.

Camera experience:
  ART menu shows "胶片色彩" (instead of "针孔相机效果")
  Right-key I/II/III = three film looks, no vignette, no blur.
  9-knot non-linear chroma curves for shadow/midtone/highlight control.

This is the recommended flash package for daily use.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.film_update import build_update
from tools.inspect_ep5 import CPU_BASE, check_stock
from tools.native_film_curves_hq import HQ_LOOKS, build_hq_table
from tools.build_native_film_trio import SLOTS, NEUTRAL_CASE, _IDENTITY, SIZE, CARD_FILE
from tools.build_native_film_pack import _fit_label

PINHOLE_PTR_OFFSETS = [0x7e40b639 - CPU_BASE, 0x7e40b87a - CPU_BASE]
PINHOLE_PTR_VALUE = 0x7e40115c

# Default look assignment (user can change via --i/--ii/--iii)
DEFAULT_LOOKS = {"I": "velvia50_hq", "II": "portra400_hq", "III": "gold200_hq"}

def look_by_key(key):
    for l in HQ_LOOKS:
        if l.key == key:
            return l
    raise ValueError(f"unknown HQ look {key!r}")

def build_final(stock, looks, menu_name="胶片色彩"):
    check_stock(stock)
    from external.oly_fw_analysis.tools import oly_container
    main_payload = oly_container.parse(stock)[0].payload
    edits = []
    # Neutralize pinhole effect
    for off in PINHOLE_PTR_OFFSETS:
        old = struct.unpack_from("<I", main_payload, off)[0]
        assert old == PINHOLE_PTR_VALUE
        edits.append((off, struct.pack("<I", old), struct.pack("<I", 0)))
    # Per-slot curves + isolation
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
    # Menu label: rename "针孔相机效果" -> menu_name (6 UTF-16 units max)
    zh = _fit_label(menu_name)
    zht = _fit_label(menu_name)  # same for traditional
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
            raise ValueError(f"label byte length mismatch: {menu_name}")
        language_edits.append((offset, before, after))
    return build_update(stock, edits, language_edits=language_edits)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--i", default=DEFAULT_LOOKS["I"])
    p.add_argument("--ii", default=DEFAULT_LOOKS["II"])
    p.add_argument("--iii", default=DEFAULT_LOOKS["III"])
    p.add_argument("--menu-name", default="胶片色彩")
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    if args.out.exists():
        p.exit(1, f"Output already exists: {args.out}\n")
    looks = {"I": args.i, "II": args.ii, "III": args.iii}
    stock = args.stock.read_bytes()
    fw = build_final(stock, looks, args.menu_name)
    assert len(fw) == SIZE
    digest = hashlib.sha256(fw).hexdigest()
    args.out.mkdir(parents=True)
    card = args.out / CARD_FILE
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_bytes(fw)
    (args.out / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
    report = {"looks": looks, "menu_name": args.menu_name,
              "firmware_sha256": digest, "neutralized": True,
              "curve_quality": "9-knot-nonlinear",
              "status": "hardware-functional-candidate"}
    (args.out / "trio-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"built FINAL HQ: {digest}")
    print(f"  menu: {args.menu_name}")
    print(f"  I={looks['I']}  II={looks['II']}  III={looks['III']}")

if __name__ == "__main__":
    main()
