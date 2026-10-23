#!/usr/bin/env python3
"""导出 E-P5 块 0 里携带的「机身 mask ROM 图像引擎 API 清单」。

意义（第 25 轮）:
    块 0 的字符串池里有一整套 `art_*` 名字（752 条），带 `in`/`out` 标记和
    `.c` 源文件名 —— 这是**随主控固件一起下发的 ROM 侧函数名表**（供追踪用）。
    ⇒ 它直接告诉我们 **ROM 里实现了哪些艺术效果**，也就是
    「菜单没暴露、但 ROM 里已经写好了」的可解锁效果。

用法:
    python tools/art_api_inventory.py --json evidence/art_filter/rom_art_api.json
"""
import argparse
import json
import re

STR = r"D:\0_Project\01Test\ep5-fw-reverse\decoded\strings.jsonl"

# 已知的「效果顶层入口」命名规则
TOP_PATTERNS = [
    (re.compile(r"^art_effect_([0-9a-f]{2})_([a-z0-9_]+)$"), "effect"),
    (re.compile(r"^art_filter_([0-9a-f]{2})_([a-z0-9_]+)$"), "filter"),
    (re.compile(r"^art_filter_([a-z0-9_]+)$"), "filter"),
    (re.compile(r"^art_(stl2ycc2?)$"), "filter"),
    (re.compile(r"^art_(artclearline|diorama|pinhole|soft_focus|white_edge|"
                r"star_light|composite|mirror|frame|pastel_art|filter_com)$"),
     "filter"),
]

# 菜单 10 项 -> 实现名（来自第十二轮）
MENU = {
    "Pop Art": "art_composite", "Dramatic Tone": "art_filter_dramatic_tone",
    "Soft Focus": "art_soft_focus", "Pale&Light Color": "art_stl2ycc",
    "Light Tone": "art_stl2ycc2", "Grainy Film": "art_filter_rough_monochrome",
    "Pin Hole": "art_pinhole", "Diorama": "art_diorama",
    "Cross Process": "art_mirror", "Gentle Sepia": "art_filter_gentle_sepia",
}
# 录像 4 项（第十九轮）
MOVIE4 = {"Grainy Film", "Pin Hole", "Diorama", "Dramatic Tone"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(STR, encoding="utf-8")]
    arts = [(int(r["container_address"], 16) - 0x20, r["text"])
            for r in rows if re.match(r"^art_[A-Za-z0-9_]", r["text"])]
    arts.sort()
    names = {t for _, t in arts}

    # 1) 顶层效果入口
    effects = []
    for addr, t in arts:
        if t.endswith(" in") or t.endswith(" out") or t.endswith(".c"):
            continue
        for pat, kind in TOP_PATTERNS:
            m = pat.match(t)
            if m:
                effects.append({"addr": "0x%08X" % addr, "name": t, "kind": kind,
                                "id": m.group(1) if m.lastindex and m.lastindex >= 2 else None})
                break

    # 2) 每个效果下的子函数（pass / set_* / get_*）
    sub = {}
    for addr, t in arts:
        for e in effects:
            root = e["name"]
            if t.startswith(root + "_") and not t.endswith(" in") and not t.endswith(" out"):
                sub.setdefault(root, []).append(t[len(root) + 1:])
                break

    # 3) 判定与接口类
    checks = [t for _, t in arts if re.match(r"^art_(chk|mov_check|get_filterlist|"
                                            r"set_func_effect|init_filter_proc|"
                                            r"main_init|get_tsk|get_msg|send_msg)", t)
              and not t.endswith(" in") and not t.endswith(" out")]

    out = {
        "source": "E-P5 v1.8 块 0 字符串池",
        "total_art_names": len(arts),
        "effects": effects,
        "effect_subfunctions": sub,
        "checks_and_api": sorted(set(checks)),
        "menu10": MENU,
        "movie4": sorted(MOVIE4),
    }

    if not args.quiet:
        print("art_* 名字总数: %d" % len(arts))
        print("\n=== ROM 侧艺术效果入口（%d 个）===" % len(effects))
        for e in effects:
            subs = sub.get(e["name"], [])
            print("  %-10s id=%-5s %-34s 子函数 %d 个 %s"
                  % (e["kind"], e["id"] or "-", e["name"], len(subs),
                     ("例: " + ", ".join(subs[:4])) if subs else ""))
        print("\n=== 菜单未暴露的效果（候选可解锁）===")
        menu_impl = set(MENU.values())
        for e in effects:
            if e["name"] not in menu_impl:
                print("  ★ %-34s (id=%s)" % (e["name"], e["id"] or "-"))
        print("\n=== 检查 / 接口类函数 ===")
        for c in out["checks_and_api"]:
            print("   ", c)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("\n[written] %s" % args.json)


if __name__ == "__main__":
    main()
