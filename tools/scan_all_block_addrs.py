#!/usr/bin/env python3
"""全量普查：所有固件的所有块，其**运行地址**是否有落在 0x7Exxxxxx 的。

背景（第十七轮 / 第十八轮）:
    机身 mask ROM 映像（0x7Exxxxxx）**不由 .BIN 承载、也不随固件更新下发**
    —— 但那是对 E-M5 / E-PM2 两个机型（2012–2013 代）做的检验。
    本脚本把同一检验推广到**仓库内全部固件**（含 2014+ 新机型），
    一次性回答:
        「有没有任何一家的 .BIN 里，真的存在一个装载在 0x7Exxxxxx 的块？」

实现：只读容器块头（不混淆还原 payload），因此远快于完整解码。
      块头布局（tools/oly_container.py）：
        [0:2] "OE"/"OM"   [8:12] 运行地址   [12:16] payload 大小
        [16:18] 版本      [20:22] kind

用法:
    python tools/scan_all_block_addrs.py --pkg firmware [--json out.json]
"""
import argparse
import glob
import json
import lzma
import os
import struct
import sys


def read_bin(path):
    """读 .BIN；若是 .lzma/.xz 则先解压（自动识别格式）。"""
    if path.lower().endswith((".lzma", ".xz")):
        with lzma.open(path, "rb") as f:
            return f.read()
    with open(path, "rb") as f:
        return f.read()


def scan_blocks(d):
    out = []
    n = len(d)
    off = 0
    while off + 32 <= n:
        if d[off:off + 2] not in (b"OE", b"OM"):
            # 快速跳过：找下一个魔数
            j = d.find(b"OE", off + 2)
            k = d.find(b"OM", off + 2)
            cand = [x for x in (j, k) if x >= 0]
            if not cand:
                break
            off = min(cand)
            continue
        hdr = d[off:off + 32]
        addr = struct.unpack_from("<I", hdr, 8)[0]
        size = struct.unpack_from("<I", hdr, 12)[0]
        kind = struct.unpack_from("<H", hdr, 20)[0]
        sig = hdr[:2].decode("latin-1")
        if size == 0 or size > n:
            off += 4
            continue
        out.append({"file_off": off, "sig": sig, "addr": addr, "size": size,
                    "kind": kind})
        off += 32 + size + 32
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", default=None, help="固件包目录（默认仓库 firmware/）")
    ap.add_argument("--json", default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    pkg = args.pkg or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firmware")
    files = []
    for sub in ("stock", "pre_fix"):
        files += glob.glob(os.path.join(pkg, sub, "**", "*.BIN*"), recursive=True)
    files = sorted(set(files))
    if args.limit:
        files = files[:args.limit]
    print("固件文件 %d 个\n" % len(files))

    all_addrs = {}
    rom_hits = []
    rows = []
    for i, f in enumerate(files):
        name = os.path.relpath(f, pkg)
        try:
            d = read_bin(f)
        except Exception as e:
            print("  %-46s 读取失败: %s" % (name[:46], e))
            continue
        bl = scan_blocks(d)
        addrs = [(b["addr"], b["size"], b["kind"], b["sig"]) for b in bl]
        for a, s, k, sg in addrs:
            all_addrs.setdefault(a, []).append((name, s, k))
            if 0x7E000000 <= a < 0x7F000000:
                rom_hits.append({"file": name, "addr": "0x%08X" % a,
                                 "size": s, "kind": "0x%03X" % k})
        rows.append({"file": name, "blocks": [
            {"addr": "0x%08X" % a, "size": s, "kind": "0x%03X" % k}
            for a, s, k, sg in addrs]})
        print("  %-46s %d 块: %s" % (
            name[:46], len(bl),
            ", ".join("0x%08X/%d" % (a, s) for a, s, k, sg in addrs)))
        if (i + 1) % 10 == 0:
            print("    ... %d/%d" % (i + 1, len(files)), flush=True)

    print("\n=== 装载在 0x7Exxxxxx 的块 ===")
    if rom_hits:
        for h in rom_hits:
            print("  ★ %s  addr=%s size=%d kind=%s" % (
                h["file"], h["addr"], h["size"], h["kind"]))
    else:
        print("  （无）★⇒ 全部 %d 个固件里，没有任何块装载在 0x7Exxxxxx" % len(rows))

    print("\n=== 出现过的全部块地址（去重）===")
    for a in sorted(all_addrs):
        ex = all_addrs[a][0]
        print("  0x%08X  出现 %2d 次   例: %s (size=%d kind=0x%03X)" % (
            a, len(all_addrs[a]), ex[0], ex[1], ex[2]))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"files": rows,
                       "rom_hits": rom_hits,
                       "distinct_addresses": {"0x%08X" % a: len(v)
                                             for a, v in sorted(all_addrs.items())}},
                      f, indent=1)
        print("\n[written] %s" % args.json)


if __name__ == "__main__":
    main()
