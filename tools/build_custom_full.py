"""Build a CUSTOM full-7 firmware from a JSON slot assignment.

Usage:
  python tools/build_custom_full.py data/ep5-stock/OLY_E_108_1800_0000_0000.BIN \
    --config my-looks.json --out build/film-custom

Config JSON format:
{
  "slots": [
    {"slot": "soft-focus", "look": "portra400_hq", "label_zh": "人像柔暖", "label_zht": "人像柔暖"},
    {"slot": "pinhole-i", "look": "velvia50_hq", "label_zh": "胶片色彩", "label_zht": "膠片色彩"},
    {"slot": "pinhole-ii", "look": "classicchrome_hq"},
    {"slot": "pinhole-iii", "look": "gold200_hq"},
    {"slot": "diorama", "look": "ektar100_hq", "label_zh": "风景鲜艳", "label_zht": "風景鮮豔"},
    {"slot": "gentle-sepia", "look": "cinestill800t_hq", "label_zh": "电影色调", "label_zht": "電影色調"},
    {"slot": "cross-process", "look": "moriyama_bw_hq", "label_zh": "森山黑白", "label_zht": "森山黑白"}
  ]
}

Looks can be:
  - A built-in HQ key (e.g. "portra400_hq")
  - A path to a .cube file (will be fitted to 9-knot curves)
  - A path to a look-report.json from cube_to_hq.py

The builder reuses the exact same isolation mechanism as build_full_film.py
(verified neutral anchor mode 72, CMIO redirects, effect zeroing).
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.film_update import build_update
from tools.inspect_ep5 import CPU_BASE, check_stock
from tools.native_film_curves_hq import HQ_LOOKS, build_hq_table, HQLook
from tools.build_full_film import (
    SIZE, CARD_FILE, _IDENTITY, NEUTRAL_CASE, _NEUTRAL_PTRS,
    EFFECT_OFFSETS, SLOTS as DEFAULT_SLOTS,
)

SLOT_MAP = {
    "soft-focus": 0, "pinhole-i": 1, "pinhole-ii": 2, "pinhole-iii": 3,
    "diorama": 4, "gentle-sepia": 5, "cross-process": 6,
}


def resolve_look(spec):
    """Resolve a look spec to (cb_points, cr_points, name)."""
    # Built-in HQ key
    for l in HQ_LOOKS:
        if l.key == spec:
            return l.cb_points, l.cr_points, l.name_zh
    # Path to .cube or look-report.json
    p = Path(spec)
    if not p.is_absolute():
        p = ROOT / p
    if p.suffix == ".cube":
        from tools.cube_to_hq import fit_cube_to_curves
        from ep5studio.cube import parse_cube
        cube = parse_cube(p.read_bytes())
        cb, cr, report = fit_cube_to_curves(cube)
        return cb, cr, cube.title or p.stem
    if p.suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        cb = tuple(tuple(pt) for pt in data["cb_points"])
        cr = tuple(tuple(pt) for pt in data["cr_points"])
        return cb, cr, data.get("name_zh", p.stem)
    raise ValueError(f"unknown look spec: {spec!r}")


def build_custom(stock, config):
    check_stock(stock)
    from external.oly_fw_analysis.tools import oly_container
    main_payload = oly_container.parse(stock)[0].payload
    edits = []
    # 1. Zero ALL effect function pointers
    for addr in EFFECT_OFFSETS:
        off = addr - CPU_BASE
        old = struct.unpack_from("<I", main_payload, off)[0]
        edits.append((off, struct.pack("<I", old), struct.pack("<I", 0)))
    # 2. Per-slot curves
    slots = [dict(s) for s in DEFAULT_SLOTS]  # copy
    for assignment in config["slots"]:
        idx = SLOT_MAP[assignment["slot"]]
        s = slots[idx]
        cb_pts, cr_pts, name = resolve_look(assignment["look"])
        cb = build_hq_table(cb_pts)
        cr = build_hq_table(cr_pts)
        edits.append((s["pair"] - CPU_BASE, _IDENTITY * 2, cb + cr))
        jt_off = s["jt"] - CPU_BASE
        jt_old = struct.unpack_from("<I", main_payload, jt_off)[0]
        edits.append((jt_off, struct.pack("<I", jt_old), struct.pack("<I", NEUTRAL_CASE)))
        for off, old, new in s["cmio"]:
            if old == new:
                continue
            edits.append((off - CPU_BASE, struct.pack("<I", old), struct.pack("<I", new)))
        # Override labels if provided
        if assignment.get("label_zh"):
            s["label_zh"] = assignment["label_zh"]
        if assignment.get("label_zht"):
            s["label_zht"] = assignment["label_zht"]
    # 2b. Soft-focus CMIO self-refs -> neutral 72 family
    for off, idx in ((0x7e21ced9, 1), (0x7e21ceee, 2), (0x7e21cf19, 4), (0x7e21cf2f, 5)):
        old = struct.unpack_from("<I", main_payload, off - CPU_BASE)[0]
        edits.append((off - CPU_BASE, struct.pack("<I", old), struct.pack("<I", _NEUTRAL_PTRS[idx])))
    # 3. Menu labels (NUL-padded to fixed capacity)
    language_edits = []
    for s in slots:
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
    return build_update(stock, edits, language_edits=language_edits), slots


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--config", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    if args.out.exists():
        p.exit(1, f"Output already exists: {args.out}\n")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    stock = args.stock.read_bytes()
    fw, slots = build_custom(stock, config)
    assert len(fw) == SIZE
    digest = hashlib.sha256(fw).hexdigest()
    args.out.mkdir(parents=True)
    card = args.out / CARD_FILE
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_bytes(fw)
    (args.out / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
    report = {"slots": [{"look": config["slots"][i]["look"] if i < len(config["slots"]) else s["look"],
                         "label": s.get("label_zh")} for i, s in enumerate(slots)],
              "firmware_sha256": digest, "total_slots": 7,
              "status": "hardware-functional-candidate"}
    (args.out / "full-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Write labels for verification
    labels = []
    for s in slots:
        if s.get("label_zh") and s.get("lang_off"):
            labels.append({"off": hex(s["lang_off"]), "want": s["label_zh"]})
        if s.get("label_zht") and s.get("lang_zht_off"):
            labels.append({"off": hex(s["lang_zht_off"]), "want": s["label_zht"]})
    (args.out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"built CUSTOM 7-slot film: {digest}")
    for s in slots:
        print(f"  {s.get('label_zh') or '(子变体)':8s}")


if __name__ == "__main__":
    main()
