#!/usr/bin/env python3
"""解析 E-P5 块 0 的「UI 字符串资源描述符表」。

结构（观察, E-P5 v1.8 块 0, 基址 0x402C0000）:
    记录长度 28 字节, 字段:
        +0x00 u32  resource_id      —— 资源 ID（本表内递增, 0x36..0x92 后跳到 0x9D..0xA2）
        +0x04 u32  0
        +0x08 u32  0
        +0x0C u32  mask_rom_ptr     —— 指向机身 mask ROM 的描述符
        +0x10 u32  type             —— 11 / 4 / 12 / 10 / 9 / 7 等
        +0x14 u32  flags            —— 位标志（可见性/分组）
        +0x18 u32  0

用法:
    python parse_res_desc_table.py --blk0 <blk0.bin> [--base 0x402C0000]
                                   [--at 0x18BEC] [--json out.json]
"""
import argparse
import json
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--at", default="0x18BEC", help="首条记录 file 偏移")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk0, "rb").read()
    p = int(args.at, 0)

    recs = []
    while p + 28 <= len(d):
        rid, z1, z2, rom, typ, flags, z3 = struct.unpack_from("<7I", d, p)
        if not (0x7E000000 <= rom < 0x7F000000) or rid > 0x2000:
            break
        recs.append({"rt": "0x%08X" % (base + p), "id": rid,
                     "rom_ptr": "0x%08X" % rom, "type": typ, "flags": flags})
        p += 28

    print("UI 资源描述符表  file 0x%08X  rt 0x%08X  共 %d 条" % (
        int(args.at, 0), base + int(args.at, 0), len(recs)))
    print("%-12s %-6s %-12s %-6s %s" % ("rt", "id", "rom_ptr", "type", "flags"))
    for r in recs:
        print("%-12s 0x%-4X %-12s %-6d 0x%X" % (
            r["rt"], r["id"], r["rom_ptr"], r["type"], r["flags"]))

    ids = [r["id"] for r in recs]
    print()
    print("ID 范围 0x%X..0x%X；表内缺号: %s" % (
        ids[0], ids[-1],
        ", ".join("0x%X" % i for i in range(ids[0], ids[-1] + 1) if i not in set(ids))))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"source": {"file": args.blk0, "block0_base": "0x%08X" % base},
                       "record_size": 28, "records": recs}, f, indent=1)
        print("[written] %s" % args.json)


if __name__ == "__main__":
    main()
