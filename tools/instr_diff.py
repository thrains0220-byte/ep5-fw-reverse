#!/usr/bin/env python3
"""指令级差分：同一地址区间内逐条比较反汇编结果。

适用场景
--------
两个版本之间，**某段代码没有搬家**（地址不变、指令边界不变）时，
字节级差分会把「立即数改写」和「分支偏移改写」混在一起；
指令级差分可以区分：

  * 同地址、同助记符、操作数不同  → **常量/偏移被改写**（语义改动）
  * 某地址只有一侧有指令          → 插入 / 删除 / 指令变长

用法::

    python instr_diff.py --a A_block0.bin --b B_block0.bin \
        --base 0x402C0000 --lo 0x403D0000 --hi 0x403E0000 [--json out.json]
"""
import argparse
import json
import re
import subprocess
import sys

OBJDUMP = "/home/sanyu/Projects/work/ep5-fw-reverse/toolchain/binutils/objdump"
LINE_RE = re.compile(r"^\s*([0-9a-f]+):\t([0-9a-f ]+)\t(\S+)\s*(.*)$")


def disasm(path, base, lo, hi):
    cmd = [OBJDUMP, "-D", "-b", "binary", "-m", "mn10300", "--insn-width=16",
           f"--start-address={lo - base}", f"--stop-address={hi - base}", path]
    out = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    ins = {}
    for line in out.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        off = int(m.group(1), 16)
        mn = m.group(3).strip()
        ops = m.group(4).strip()
        ins[base + off] = (mn, ops)
    return ins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x402C0000)
    ap.add_argument("--lo", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--hi", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--max", type=int, default=120)
    args = ap.parse_args()

    A = disasm(args.a, args.base, args.lo, args.hi)
    B = disasm(args.b, args.base, args.lo, args.hi)
    print(f"区间 0x{args.lo:08X}-0x{args.hi:08X}   A 指令 {len(A)}  B 指令 {len(B)}")

    only_a, only_b, diff_ops = [], [], []
    for addr in sorted(set(A) | set(B)):
        ia = A.get(addr)
        ib = B.get(addr)
        if ia and ib:
            if ia != ib:
                diff_ops.append((addr, ia, ib))
        elif ia:
            only_a.append((addr, ia))
        else:
            only_b.append((addr, ib))

    print(f"操作数不同: {len(diff_ops)}   仅 A 有: {len(only_a)}   仅 B 有: {len(only_b)}\n")

    print("=== 同地址、指令不同（常量/偏移被改写）===")
    for addr, ia, ib in diff_ops[: args.max]:
        print(f"  0x{addr:08X}  A: {ia[0]:<8s} {ia[1]}")
        print(f"  {'':11s}  B: {ib[0]:<8s} {ib[1]}")
    if only_a or only_b:
        print("\n=== 仅单侧存在的指令（插入/删除/变长）===")
        for addr, i in only_a[: args.max]:
            print(f"  0x{addr:08X}  A: {i[0]:<8s} {i[1]}")
        for addr, i in only_b[: args.max]:
            print(f"  0x{addr:08X}  B: {i[0]:<8s} {i[1]}")

    if args.json:
        json.dump({
            "range": [args.lo, args.hi],
            "diff_ops": [{"addr": a, "a": list(x), "b": list(y)} for a, x, y in diff_ops],
            "only_a": [{"addr": a, "i": list(x)} for a, x in only_a],
            "only_b": [{"addr": a, "i": list(x)} for a, x in only_b],
        }, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n[JSON] {args.json}")


if __name__ == "__main__":
    main()
