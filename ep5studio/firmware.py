"""Desktop-side firmware builder: assign looks to the 7 verified ART slots,
build a custom full-7 firmware, and package it with recovery.

This is the REAL camera path (chroma curves, pure data patch).
It does NOT use the SD LUT runtime (which is still pending hardware proof).
"""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.native_film_curves_hq import HQ_LOOKS

# The 7 verified reachable slots (from build_full_film.py / ART_SLOT_AUDIT)
FW_SLOTS = [
    {"id": "soft-focus", "menu": "人像柔暖", "original": "柔焦效果", "mode": 69},
    {"id": "pinhole-i", "menu": "胶片色彩 I", "original": "针孔相机 I", "mode": 73},
    {"id": "pinhole-ii", "menu": "胶片色彩 II", "original": "针孔相机 II", "mode": 106},
    {"id": "pinhole-iii", "menu": "胶片色彩 III", "original": "针孔相机 III", "mode": 108},
    {"id": "diorama", "menu": "风景鲜艳", "original": "立体效果", "mode": 86},
    {"id": "gentle-sepia", "menu": "电影色调", "original": "浓郁色调效果", "mode": 91},
    {"id": "cross-process", "menu": "森山黑白", "original": "负片冲印效果", "mode": 153},
]

# Default assignment (matches the verified full-7 build)
DEFAULT_ASSIGNMENT = {
    "soft-focus": "portra400_hq",
    "pinhole-i": "velvia50_hq",
    "pinhole-ii": "classicchrome_hq",
    "pinhole-iii": "gold200_hq",
    "diorama": "ektar100_hq",
    "gentle-sepia": "cinestill800t_hq",
    "cross-process": "moriyama_bw_hq",
}


def available_hq_looks():
    """Return the built-in HQ looks as (key, name_zh, note) tuples."""
    return [(l.key, l.name_zh, l.note) for l in HQ_LOOKS]


def build_firmware_from_assignment(stock_path: Path, assignment: dict,
                                   labels: dict | None = None,
                                   out_dir: Path | None = None):
    """Build a custom full-7 firmware.

    assignment: {slot_id: look_key_or_cube_path}
    labels: {slot_id: {"zh": "...", "zht": "..."}} (optional menu renames)
    out_dir: output directory (must not exist)

    Returns (firmware_bytes, sha256, report_dict).
    """
    from tools.build_custom_full import build_custom, SLOT_MAP
    from tools.build_full_film import SIZE, CARD_FILE

    config = {"slots": []}
    for slot_id, look_spec in assignment.items():
        if slot_id not in SLOT_MAP:
            raise ValueError(f"unknown slot: {slot_id}")
        entry = {"slot": slot_id, "look": look_spec}
        if labels and slot_id in labels:
            entry["label_zh"] = labels[slot_id].get("zh", "")
            entry["label_zht"] = labels[slot_id].get("zht", "")
        config["slots"].append(entry)

    stock = stock_path.read_bytes()
    fw, slots = build_custom(stock, config)
    assert len(fw) == SIZE
    digest = hashlib.sha256(fw).hexdigest()

    report = {
        "slots": [{"slot": s.get("label_zh") or SLOT_MAP_INV[i],
                   "look": assignment.get(SLOT_MAP_INV[i], ""),
                   "label": s.get("label_zh")}
                  for i, s in enumerate(slots)],
        "firmware_sha256": digest,
        "total_slots": 7,
        "status": "hardware-functional-candidate",
    }

    if out_dir:
        out_dir = Path(out_dir)
        if out_dir.exists():
            raise FileExistsError(f"Output already exists: {out_dir}")
        out_dir.mkdir(parents=True)
        card = out_dir / CARD_FILE
        card.parent.mkdir(parents=True, exist_ok=True)
        card.write_bytes(fw)
        (out_dir / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
        (out_dir / "full-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # Write labels for verification
        labels_out = []
        for s in slots:
            if s.get("label_zh") and s.get("lang_off"):
                labels_out.append({"off": hex(s["lang_off"]), "want": s["label_zh"]})
            if s.get("label_zht") and s.get("lang_zht_off"):
                labels_out.append({"off": hex(s["lang_zht_off"]), "want": s["label_zht"]})
        (out_dir / "labels.json").write_text(
            json.dumps(labels_out, ensure_ascii=False, indent=2), encoding="utf-8")

    return fw, digest, report


SLOT_MAP_INV = {v: k for k, v in
                {"soft-focus": 0, "pinhole-i": 1, "pinhole-ii": 2, "pinhole-iii": 3,
                 "diorama": 4, "gentle-sepia": 5, "cross-process": 6}.items()}


def package_kit(stock_path: Path, fw: bytes, digest: str, out_dir: Path):
    """Package firmware + recovery into a flashable kit directory."""
    from tools.build_full_film_kit import write_archive, full_note
    from tools.inspect_ep5 import STOCK_SHA256
    from tools.build_full_film import SIZE, CARD_FILE
    import tempfile
    from contextlib import ExitStack

    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"Output already exists: {out_dir}")
    stock = stock_path.read_bytes()
    install = (ROOT / "docs/SD_TRIAL.txt").read_text(encoding="utf-8")
    recovery = ("Olympus PEN E-P5 1.8 — 原厂恢复包\n"
                f"{CARD_FILE}，{SIZE:,} 字节，SHA-256：{STOCK_SHA256}\n\n")
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    full_name = "E-P5-1.8-Film-CUSTOM-7.zip"
    rec_name = "E-P5-1.8-STOCK-RECOVERY.zip"
    with tempfile.TemporaryDirectory(dir=out_dir.parent) as tmp:
        stage = Path(tmp)
        write_archive(stage / full_name, fw, digest, full_note(digest) + "\n" + install)
        write_archive(stage / rec_name, stock, STOCK_SHA256, recovery + install)
        with ExitStack() as rollback:
            out_dir.mkdir(); rollback.callback(out_dir.rmdir)
            for name in (full_name, rec_name):
                (stage / name).rename(out_dir / name)
                rollback.callback((out_dir / name).unlink)
            rollback.pop_all()
    return out_dir
