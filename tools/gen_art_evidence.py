#!/usr/bin/env python3
"""生成 evidence/art_filter/ 下的证据 JSON（可复现）。

产出：
  art_effect_ids.json    —— 块 0 中 art_* 子系统的效果 ID 空间与函数名清单
  block1_filter_names.json—— 块 1 中创意滤镜 UI 名字的位置与资源 ID
  lens_info_table.json   —— 块 0 的 LENS_INFO 镜头主表
"""
import json, re, collections, os, sys, struct

REPO = r"D:\0_Project\01Test\ep5-fw-reverse"
sys.path.insert(0, r"D:\0_Project\01Test\fw-work")
import ep5_lens

B0 = os.path.join(REPO, "decoded", "00_0100_402c0020.decoded.bin")
B1 = os.path.join(REPO, "decoded", "01_0101_427c0020.decoded.bin")
SJSONL = os.path.join(REPO, "decoded", "strings.jsonl")
BASE = 0x402C0000
OUT = os.path.join(REPO, "evidence", "art_filter")
os.makedirs(OUT, exist_ok=True)

rows = [json.loads(l) for l in open(SJSONL, encoding="utf-8")]

# ---------------- 1. art 效果 ID 空间 ----------------
eff = collections.defaultdict(set)
art_funcs = []
for r in rows:
    if r["block"] != 0:
        continue
    t = r["text"]
    m = re.match(r"^art_effect_(\d+)_([A-Za-z0-9_]+)$", t)
    if m:
        eff[int(m.group(1))].add(m.group(2))
        continue
    if re.match(r"^art_[A-Za-z0-9_]+$", t):
        art_funcs.append({"name": t, "block0_offset": r["decoded_offset"],
                          "runtime_addr": hex(BASE + int(r["decoded_offset"], 16))})

art1 = {
    "note": "块 0 中 art_*（艺术/创意滤镜）子系统的符号名清单。均为静态字符串观察，"
            "不含执行证据。",
    "source": {"file": "decoded/00_0100_402c0020.decoded.bin",
               "block0_base": hex(BASE), "strings_index": "decoded/strings.jsonl"},
    "effect_id_space": [
        {"effect_id": k, "names": sorted(v),
         "interpretation": {"10": "star_light (星光)", "20": "pinhole (针孔)",
                            "30": "frame (画框)", "40": "soft_focus (柔焦)",
                            "50": "white_edge (白边)"}.get(str(k), "")}
        for k, v in sorted(eff.items())
    ],
    "art_function_names": sorted(set(f["name"] for f in art_funcs)),
    "control_functions": sorted(n for n in set(f["name"] for f in art_funcs)
                                if not re.match(r"^art_[a-z_]+_pass\d+$", n)
                                and not n.startswith("art_effect_")),
}
json.dump(art1, open(os.path.join(OUT, "art_effect_ids.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"art_effect_ids.json: {len(eff)} 个效果 ID, {len(art1['art_function_names'])} 个函数名")

# ---------------- 2. 块 1 滤镜 UI 名字 ----------------
d1 = open(B1, "rb").read()
N1 = len(d1)


def u16_strings(minlen=3):
    out = []
    i = 0
    while i < N1 - 4:
        if d1[i + 1] == 0 and 0x20 <= d1[i] < 0x7F:
            j = i
            ch = []
            while j + 1 < N1 and d1[j + 1] == 0 and (0x20 <= d1[j] < 0x7F):
                ch.append(chr(d1[j]))
                j += 2
            if len(ch) >= minlen:
                out.append((i, "".join(ch)))
                i = j
                continue
        i += 1
    return out


u16 = u16_strings(3)
NAMES = ["i-Enhance", "Vivid", "Portrait", "Pop Art", "Soft Focus",
         "Pale&Light Color", "Light Tone", "Grainy Film", "Pin Hole", "Diorama",
         "Cross Process", "Dramatic Tone", "Gentle Sepia", "Water Color",
         "Toned Color", "Star Light", "White Edge", "F.I.X.", "Natural",
         "Muted", "Monochrome", "Pop Art"]
found = collections.defaultdict(list)
for off, t in u16:
    core = t
    m = re.match(r"^@?(A0[0-9A-F]{2})@(.*)$", t)
    rid = None
    if m:
        rid, core = m.group(1), m.group(2)
    core = core.strip()
    for n in NAMES:
        if core == n or (len(core) > 2 and core.startswith(n) and n in ("Pin Hole", "Cross Process")):
            found[n].append({"block1_offset": hex(off), "resource_id": rid, "text": t})
            break

art2 = {
    "note": "块 1 = UTF-16LE 多语言 UI 字符串池（每条以 UTF-16 NUL 结束）。"
            "此处记录 E-P5 照片模式/艺术滤镜相关名字及其在块 1 中的位置。"
            "'@A0xx@' 前缀是菜单项的字符串资源 ID（静态观察，语义待定）。",
    "source": {"file": "decoded/01_0101_427c0020.decoded.bin",
               "block1_base": "0x427c0000", "block1_size": N1},
    "utf16_string_count": len(u16),
    "filter_names": {k: v for k, v in sorted(found.items())},
}
json.dump(art2, open(os.path.join(OUT, "block1_filter_names.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"block1_filter_names.json: {len(found)} 个名字")

# ---------------- 3. LENS_INFO 镜头主表 ----------------
d0 = open(B0, "rb").read()
start, recs = ep5_lens.find_lens_info_table(d0, BASE)
art3 = {
    "note": "块 0 数据段的 LENS_INFO 镜头主表。8 字节记录："
            "{uint16 category, uint16 slot, uint8 maker, uint8 model, uint16 extra}。"
            "maker/model 即 4 字节镜头 ID 的高两字节。定位依据："
            "字符串 'LENS_INFO SIZE' 之前、ASCII 字符串区起点处的连续记录。",
    "source": {"file": "decoded/00_0100_402c0020.decoded.bin", "block0_base": hex(BASE)},
    "table_start": hex(BASE + start) if start is not None else None,
    "record_count": len(recs),
    "records": [{"addr": hex(a), "category": c, "slot": hex(s),
                 "lens_id": f"{mk:02X}:{mo:02X}", "extra": hex(ex)}
                for a, c, s, mk, mo, ex in recs],
    "unique_lens_ids": sorted({f"{mk:02X}:{mo:02X}" for _, _, _, mk, mo, _ in recs}),
}
json.dump(art3, open(os.path.join(OUT, "lens_info_table.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"lens_info_table.json: {len(recs)} 条记录")
print("已写入", OUT)
