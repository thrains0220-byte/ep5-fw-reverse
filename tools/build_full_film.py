"""Build FULL 7-slot film firmware: all reachable independent chroma groups neutralized.

Camera experience:
  ART menu shows 6 renamed entries, 7 independent film looks:
    柔焦     → "人像柔暖"   (Portra 400)
    针孔 I   → "浓艳反转"   (Velvia 50)
    针孔 II  → "经典铬"     (Classic Chrome)
    针孔 III → "暖金负片"   (Gold 200)
    立体效果 → "风景鲜艳"   (Ektar 100)
    浓郁色调 → "电影色调"   (CineStill)
    负片冲印 → "森山黑白"   (Moriyama B&W)

All effects neutralized (no vignette/blur/sepia/star/mirror).
9-knot non-linear HQ curves. Movie modes rerouted to factory neutral.
Pure data patch, same risk as verified RC2.

Note: star_light (mode 118) is NOT menu-reachable on E-P5; it is omitted.
composite (mode 153) = Cross Process = 负片冲印, which IS menu-reachable.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.film_update import build_update
from tools.inspect_ep5 import CPU_BASE, check_stock
from tools.native_film_curves_hq import HQ_LOOKS, build_hq_table
from tools.build_native_film_pack import _fit_label

SIZE = 44_826_624
CARD_FILE = "DCOLYMP/E1089999.BIN"
_X = bytes([0]*4 + [64,128,192] + [255]*9)
_IDENTITY = _X + _X + bytes([0]*4 + [128]*4 + [0]*9)
# Neutral anchor: mode 72's factory case. Mode 72 is gate=1 (unreachable as a
# photo slot per ART_SLOT_AUDIT) and its six curve tables are byte-identical to
# mode 69's factory identity. We must NOT use mode 69 as the anchor because 69
# is the reachable soft-focus photo slot (REC 101/113) that carries Portra.
NEUTRAL_CASE = 0x7e22a0eb
# Neutral CMIO target family = mode 72's six pointers (identity content).
_NEUTRAL_PTRS = [0x7e438b4e, 0x7e438b5e, 0x7e438b6e, 0x7e438b7f, 0x7e438b8f, 0x7e438b9f]

# All effect MOV offsets to zero (from probe)
EFFECT_OFFSETS = [
    0x7e40b810,  # soft_focus
    0x7e40b639, 0x7e40b87a,  # pinhole (2)
    0x7e40b679,  # gentle_sepia
    0x7e40b651,  # dramatic_tone
    0x7e40b661,  # artclearline
    0x7e40b682,  # pastel_art
    0x7e40b641,  # rough_mono
    0x7e40b649,  # diorama
    0x7e40b659, 0x7e40b7e1,  # star_light (2)
    0x7e40b669,  # mirror
    0x7e40b671,  # composite
]

# 7 independent slots — CMIO data from build/cmio-all-groups.json (verified).
# Mode 69 CMIO is self-referential (already neutral), so no CMIO edits needed.
# Mode 153 has no CMIO refs found; only pair + JT reroute.
SLOTS = [
    # Soft focus: mode 69, shared 78. 69 is a real photo slot (REC 101/113).
    # Its CMIO refs are self-referential; redirect them to the 72 neutral family
    # so the shared/movie path stays factory while photo 69 carries Portra.
    {"pair": 0x7e438a28, "jt": 0x7e478eb4, "cmio": [],
     "look": "portra400_hq", "label_zh": "人像柔暖", "label_zht": "人像柔暖",
     "lang_off": 0x2ce1f8, "lang_icon_off": 0x2d0844,
     "lang_old": "柔焦效果", "lang_icon_old": "@A041@柔焦效果",
     "lang_zht_off": 0x2db40a, "lang_zht_icon_off": 0x2dda8c,
     "lang_zht_old": "柔焦效果", "lang_zht_icon_old": "@A041@柔焦效果"},
    # Pinhole I: mode 73, shared 82
    {"pair": 0x7e438bb0, "jt": 0x7e478ec4,
     "cmio": [(0x7e21d0e7, 0x7e438bc0, 0x7e438a38),
              (0x7e21d0fd, 0x7e438bd0, 0x7e438a48),
              (0x7e21d129, 0x7e438bf1, 0x7e438a69),
              (0x7e21d13f, 0x7e438c01, 0x7e438a79)],
     "look": "velvia50_hq", "label_zh": "胶片色彩", "label_zht": "膠片色彩",
     "lang_off": 0x2ce202, "lang_icon_off": 0x2d08ae,
     "lang_old": "针孔相机效果", "lang_icon_old": "@A045@针孔相机效果",
     "lang_zht_off": 0x2db414, "lang_zht_icon_off": 0x2ddaf8,
     "lang_zht_old": "針孔相機效果", "lang_zht_icon_old": "@A045@針孔相機效果"},
    # Pinhole II: mode 106, shared 107
    {"pair": 0x7e438dfc, "jt": 0x7e478f28,
     "cmio": [(0x7e21d3ff, 0x7e438e0c, 0x7e438a38),
              (0x7e21d415, 0x7e438e1c, 0x7e438a48),
              (0x7e21d441, 0x7e438e3d, 0x7e438a69),
              (0x7e21d457, 0x7e438e4d, 0x7e438a79)],
     "look": "classicchrome_hq", "label_zh": None, "label_zht": None},
    # Pinhole III: mode 108, shared 109
    {"pair": 0x7e438e5e, "jt": 0x7e478f30,
     "cmio": [(0x7e21d483, 0x7e438e6e, 0x7e438a38),
              (0x7e21d499, 0x7e438e7e, 0x7e438a48),
              (0x7e21d4c5, 0x7e438e9f, 0x7e438a69),
              (0x7e21d4db, 0x7e438eaf, 0x7e438a79)],
     "look": "gold200_hq", "label_zh": None, "label_zht": None},
    # Diorama: mode 86, shared 88
    {"pair": 0x7e438c12, "jt": 0x7e478edc,
     "cmio": [(0x7e21d16b, 0x7e438c22, 0x7e438a38),
              (0x7e21d181, 0x7e438c32, 0x7e438a48),
              (0x7e21d1ad, 0x7e438c53, 0x7e438a69),
              (0x7e21d1c3, 0x7e438c63, 0x7e438a79)],
     "look": "ektar100_hq", "label_zh": "风景鲜艳", "label_zht": "風景鮮豔",
     "lang_off": 0x2ce19c, "lang_icon_off": 0x2d08c8,
     "lang_old": "立体效果", "lang_icon_old": "@A046@立体效果",
     "lang_zht_off": 0x2db3a8, "lang_zht_icon_off": 0x2ddb12,
     "lang_zht_old": "透視效果", "lang_zht_icon_old": "@A046@透視效果"},
    # Gentle sepia: mode 91, shared 93
    {"pair": 0x7e438cd6, "jt": 0x7e478ef0,
     "cmio": [(0x7e21d273, 0x7e438ce6, 0x7e438a38),
              (0x7e21d289, 0x7e438cf6, 0x7e438a48),
              (0x7e21d2b5, 0x7e438d17, 0x7e438a69),
              (0x7e21d2cb, 0x7e438d27, 0x7e438a79)],
     "look": "cinestill800t_hq", "label_zh": "电影色调", "label_zht": "電影色調",
     "lang_off": 0x2ce1ea, "lang_icon_off": 0x2d082a,
     "lang_old": "浓郁色调效果", "lang_icon_old": "@A03F@浓郁色调效果",
     "lang_zht_off": 0x2db3fc, "lang_zht_icon_off": 0x2dda72,
     "lang_zht_old": "濃化色調效果", "lang_zht_icon_old": "@A03F@濃化色調效果"},
    # Composite / Cross Process: mode 153, shared 154 — no CMIO refs found
    {"pair": 0x7e438f84, "jt": 0x7e478fe4, "cmio": [],
     "look": "moriyama_bw_hq", "label_zh": "森山黑白", "label_zht": "森山黑白",
     "lang_off": 0x2ce18e, "lang_icon_off": 0x2d0686,
     "lang_old": "负片冲印效果", "lang_icon_old": "@A047@负片冲印效果",
     "lang_zht_off": 0x2db39a, "lang_zht_icon_off": 0x2dd8d2,
     "lang_zht_old": "負片冲印效果", "lang_zht_icon_old": "@A047@負片冲印效果"},
]

def look_by_key(key):
    for l in HQ_LOOKS:
        if l.key == key:
            return l
    raise ValueError(f"unknown look {key}")

def build_full(stock):
    check_stock(stock)
    from external.oly_fw_analysis.tools import oly_container
    main_payload = oly_container.parse(stock)[0].payload
    edits = []
    # 1. Zero ALL effect function pointers
    for addr in EFFECT_OFFSETS:
        off = addr - CPU_BASE
        old = struct.unpack_from("<I", main_payload, off)[0]
        edits.append((off, struct.pack("<I", old), struct.pack("<I", 0)))
    # 2. Per-slot chroma curves + shared mode reroute + CMIO
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
                continue  # skip no-op
            edits.append((off - CPU_BASE, struct.pack("<I", old), struct.pack("<I", new)))
    # 2b. Soft-focus (69) CMIO self-refs must point to the neutral 72 family,
    # otherwise the shared/movie path would copy Portra. The four second-axis
    # literals for 69 are at 0x7e21ced9/eee/0x7e21cf19/cf2f (from art-full.json).
    for off, idx in ((0x7e21ced9, 1), (0x7e21ceee, 2), (0x7e21cf19, 4), (0x7e21cf2f, 5)):
        old = struct.unpack_from("<I", main_payload, off - CPU_BASE)[0]
        edits.append((off - CPU_BASE, struct.pack("<I", old), struct.pack("<I", _NEUTRAL_PTRS[idx])))
    # 3. Menu labels. Entries have fixed UTF-16 capacity; pad with NUL to keep
    # the byte length identical (a trailing U+3000 would render as a space).
    language_edits = []
    for s in SLOTS:
        if not s.get("label_zh") or not s.get("lang_off"):
            continue
        zh = s["label_zh"]
        zht = s.get("label_zht", s["label_zh"])
        # Simplified plain
        old_text = s["lang_old"]
        before = (old_text + "\0").encode("utf-16-le")
        after = (zh + "\0" * (len(old_text) - len(zh) + 1)).encode("utf-16-le")
        if len(before) == len(after):
            language_edits.append((s["lang_off"], before, after))
        # Simplified icon
        if s.get("lang_icon_off") and s.get("lang_icon_old"):
            prefix = s["lang_icon_old"].split(old_text)[0]
            before = (prefix + old_text + "\0").encode("utf-16-le")
            after = (prefix + zh + "\0" * (len(old_text) - len(zh) + 1)).encode("utf-16-le")
            if len(before) == len(after):
                language_edits.append((s["lang_icon_off"], before, after))
        # Traditional plain
        if s.get("lang_zht_off") and s.get("lang_zht_old"):
            old_zht = s["lang_zht_old"]
            before = (old_zht + "\0").encode("utf-16-le")
            after = (zht + "\0" * (len(old_zht) - len(zht) + 1)).encode("utf-16-le")
            if len(before) == len(after):
                language_edits.append((s["lang_zht_off"], before, after))
        # Traditional icon
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
    fw = build_full(stock)
    assert len(fw) == SIZE
    digest = hashlib.sha256(fw).hexdigest()
    args.out.mkdir(parents=True)
    card = args.out / CARD_FILE
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_bytes(fw)
    (args.out / "SHA256SUMS").write_text(f"{digest}  {CARD_FILE}\n", encoding="ascii")
    report = {"slots": [{"look": s["look"], "label": s.get("label_zh")} for s in SLOTS],
              "firmware_sha256": digest, "total_slots": 7,
              "neutralized_effects": len(EFFECT_OFFSETS),
              "status": "hardware-functional-candidate"}
    (args.out / "full-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"built FULL 7-slot film: {digest}")
    for s in SLOTS:
        print(f"  {s.get('label_zh') or '(子变体)':8s} = {s['look']}")

if __name__ == "__main__":
    main()
