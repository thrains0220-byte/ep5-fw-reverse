#!/usr/bin/env python3
"""在块 0 里找「菜单描述符选择函数」的字节指纹。

指纹（由 E-P5 的 `FUN_403E7E94` 归纳）:
    一串 `mov <imm32>,D0`（MN103 编码 `fc dc <imm32 LE>`），
    立即数落在 `0x7Exxxxxx`（mask ROM），且**相邻两个的间距 ≤ 0x40 且递增**。
    这样的成组立即数就是一个「按类型码返回不同 ROM 描述符」的函数体。

用途:
    比较不同机型（录像艺术菜单项数不同）的描述符函数：
      * E-M5 II v3.0  / E-M1 III v1.2 / E-M5 III v1.4 / E-M10 III v1.2  → 录像菜单 **10** 项
      * E-P5 v1.8 / E-M1 v4.6                                       → 录像菜单 **4** 项
      * E-M5 II v4.1 / E-M10 II v1.4                                → 录像菜单 **5** 项
    ⇒ 看「10 项那一档」的描述符地址，在 E-P5 的 ROM 地址空间里**存不存在**。

用法:
    python tools/find_rom_desc_tables.py --blk0 <块0> [--label 名字] [--min 3]
"""
import argparse
import struct


def find_runs(d, base=0, lo=0x7E000000, hi=0x7F000000, max_stride=0x40, min_n=3):
    """找出成组的 `fc dc <imm32>`（imm32 在 ROM 区间、递增、间距 ≤ max_stride）。"""
    n = len(d)
    # 收集所有 fc dc 的位置与立即数
    items = []
    i = 0
    while True:
        i = d.find(b"\xfc\xdc", i)
        if i < 0:
            break
        if i + 6 <= n:
            v = struct.unpack_from("<I", d, i + 2)[0]
            if lo <= v < hi:
                items.append((i, v))
        i += 1

    runs = []
    cur = []
    for it in items:
        if not cur:
            cur = [it]
            continue
        gap = it[0] - cur[-1][0]
        stride = it[1] - cur[-1][1]
        if 0 < gap <= 0x20 and 0 < stride <= max_stride:
            cur.append(it)
        else:
            if len(cur) >= min_n:
                runs.append(cur)
            cur = [it]
    if len(cur) >= min_n:
        runs.append(cur)
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--min", type=int, default=3)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--max-stride", type=lambda x: int(x, 0), default=0x40)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk0, "rb").read()
    runs = find_runs(d, base, max_stride=args.max_stride, min_n=args.min)
    print("块 0 %s  (%d B)  找到 %d 组成组 ROM 立即数 (>=%d 项)"
          % (args.label or args.blk0, len(d), len(runs), args.min))
    for r in sorted(runs, key=lambda x: -len(x))[:25]:
        addrs = [v for _, v in r]
        print("  @0x%08X  %d 项: %s" % (base + r[0][0], len(r),
                                        " ".join("0x%08X" % v for v in addrs)))
    print()
    print("提示：录像艺术菜单项数对照 ——")
    print("  10 项机型: E-M1 II v3.0 / E-M1 III v1.2 / E-M5 III v1.4 / E-M10 III v1.2")
    print("   5 项机型: E-M5 II v4.1 / E-M10 II v1.4")
    print("   4 项机型: E-P5 v1.8 / E-M1 v4.6")


if __name__ == "__main__":
    main()
