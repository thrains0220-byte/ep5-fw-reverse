"""Build SAFE 7-slot film firmware: RC2-verified mechanism, effects PRESERVED.

This is the conservative fallback after the full-neutralization build caused
ART black-screen on hardware. The proven RC2 mechanism only changes chroma
curves + isolates shared/movie modes; it NEVER zeros effect function pointers.

Camera experience (factory spatial effects remain):
  柔焦     → "人像柔暖"   (Portra 400)  + factory soft focus
  针孔 I   → "胶片色彩"   (Velvia 50)   + factory pinhole vignette
  针孔 II  →              (Classic Chrome) + factory pinhole vignette
  针孔 III →              (Gold 200)    + factory pinhole vignette
  立体效果 → "风景鲜艳"   (Ektar 100)   + factory diorama blur
  浓郁色调 → "电影色调"   (CineStill)   + factory gentle sepia tint
  负片冲印 → "森山黑白"   (Moriyama B&W) + factory cross-process

All chroma curves are HQ 9-knot non-linear. Movie modes rerouted to factory
neutral (mode 72 anchor). Pure data patch, identical risk class to RC2 which
booted, captured full-size RAW+JPEG, and recovered on a real E-P5.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.film_update import build_update
from tools.inspect_ep5 import CPU_BASE, check_stock
from tools.native_film_curves_hq import HQ_LOOKS, build_hq_table
from tools.build_full_film import (
    SIZE, CARD_FILE, _IDENTITY, NEUTRAL_CASE, _NEUTRAL_PTRS, SLOTS,
)


def look_by_key(key):
    for l in HQ_LOOKS:
        if l.key == key:
            return l
    raise ValueError(f"unknown look {key}")


def build_safe(stock):
    check_stock(stock)
    from external.oly_fw_analysis.tools import oly_container
    main_payload = oly_container.parse(stock)[0].payload
    edits = []
    # NO effect pointer zeroing. Factory effects preserved (RC2-verified).
    # Per-slot chroma curves + shared mode reroute + CMIO isolation.
    for s in SLOTS:
        look = look_by_key(s["look"])
        cb = build_hq_table(look.cb_points)
        cr = build_hq_table(look.cr_points)
        edits.append((s["pair"] - CPU_BASE, _IDENTITY * 2, cb + cr))
        jt_off = s["jt"] - CPU_BASE
        jt_old = struct.unpack_from("<I", main_payload, jt_off)[0]
        edits.append((jt_off, struct.pack("<I", jt_old), struct.pack("<I", NEUTRAL_CASE)))
        for off, old, new in s["cmio"]:
            if old == new:
                continue
            edits.append((off - CPU_BASE, struct.pack("<I", old), struct.pack("<I", new)))
    # Soft-focus (69) CMIO self-refs -> neutral 72 family (keep movie factory).
    for off, idx in ((0x7e21ced9, 1), (0x7e21ceee, 2), (0x7e21cf19, 4), (0x7e21cf2f, 5)):
        old = struct.unpack_from("<I", main_payload, off - CPU_BASE)[0]
        edits.append((off - CPU_BASE, struct.pack("<I", old), struct.pack("<I", _NEUTRAL_PTRS[idx])))
    # Menu labels (NUL-padded to fixed capacity).
    language_edits = []
    for s in SLOTS:
        if not s.get("label_zh") or not s.get("lang_off"):
            continue
        zh = s["label_zh"]
        zht = s.get("label_zht", zh)
        old_text = s["lang_old"]
        before = (old_text + "\0").encode("utf-16-le")
        after = (zh + "\0" * (len(old_text) - len(zh) + 1)).encode("utf-16-le")
        if len(before) == len(after):
            language_edits.append((s["lang_off"], before, after))
        if s.get("lang_icon_off") and s.get("lang_icon_old"):
            prefix = s["lang_icon_old"].split(old_text)[0]
            before = (prefix + old_text + "\0").encode("utf-16-le")
            after = (prefix + zh + "\0" * (len(old_text) - len(zh) + 1)).encode("utf-16-le")
            if len(before) == len(after):
                language_edits.append((s["lang_icon_off"], before, after))
        if s.get("lang_zht_off") and s.get("lang_zht_old"):
            old_zht = s["lang_zht_old"]
            before = (old_zht + "\0").encode("utf-16-le")
            after = (zht + "\0" * (len(old_zht) - len(zht) + 1)).encode("utf-16-le")
            if len(before) == len(after):
                language_edits.append((s["lang_zht_off"], before, after))
        if s.get("lang_zht_icon_off") and s.get("lang_zht_icon_old"):
            prefix = s["lang_zht_icon_old"].split(s["lang_zht_old"])[0]
            before = (prefix + s["lang_zht_old"] + "\0").encode("utf-16-le")
            after = (prefix + zht + "\0" * (len(s["lang_zht_old"]) - len(zht) + 1)).encode("utf-16-le")
            if len(before) == len(after):
                language_edits.append((s["lang_zht_icon_off"], before, after))
    return build_update(stock, edits, language_edits=language_edits)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    if args.out.exists():
        p.exit(1, f"Output already exists: {args.out}\n")
    stock = args.stock.read_bytes()
    fw = build_safe(stock)
    assert len(fw) == SIZE
    digest = hashlib.sha256(fw).hexdigest()
    args.out.mkdir(parents=True)
    card = args.out / CARD_FILE
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_bytes(fw)
    (args.out / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
    report = {"slots": [{"look": s["look"], "label": s.get("label_zh")} for s in SLOTS],
              "firmware_sha256": digest, "total_slots": 7,
              "effects": "factory-preserved",
              "status": "hardware-functional-candidate"}
    (args.out / "full-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    labels = []
    for s in SLOTS:
        if s.get("label_zh") and s.get("lang_off"):
            labels.append({"off": hex(s["lang_off"]), "want": s["label_zh"]})
        if s.get("label_zht") and s.get("lang_zht_off"):
            labels.append({"off": hex(s["lang_zht_off"]), "want": s["label_zht"]})
    (args.out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"built SAFE 7-slot film (effects preserved): {digest}")
    for s in SLOTS:
        print(f"  {s.get('label_zh') or '(子变体)':8s} = {s['look']}")


if __name__ == "__main__":
    main()
