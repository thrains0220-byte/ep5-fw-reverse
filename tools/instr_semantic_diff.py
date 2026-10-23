#!/usr/bin/env python3
"""地址归一化的反汇编级语义差分。

回答的问题：两版固件代码块的字节差异里，有多少是「同一段代码被重链接
（地址变了、指令序列没变）」，有多少是「指令序列真的改了」。

做法
----
对每个版本反汇编，得到两条平行的指令流：

    shape 流：助记符 + 操作数【把所有数字字面量替换成 #】
    full  流：助记符 + 操作数【原样】

shape 相同 ⇒ 指令骨架完全一致（仅数值不同）。
full  不同 ⇒ 数值也变了。

用 GNU diff 分别对两条流做差：
    * shape diff 的 hunk  = 结构性改动（指令被增/删/替换）
    * full  diff 的 hunk  = 一切数值变化
    * full 有、shape 没有的 hunk ⇒ 纯数值变化 = 重链接候选
    * 两者都有��� hunk      ⇒ 真·结构性改动候选

对「纯数值变化」区段，再逐个 4 字节槽位比较 A/B 取值：
若差值恒为同一 delta ⇒ 确证为地址重定位。

用法:
  instr_semantic_diff.py A.bin B.bin BASE [--lo 0x200000] [--hi 0x700000]
"""
import sys, os, re, subprocess, hashlib, argparse, collections

OBJDUMP = "/home/sanyu/Projects/work/ep5-fw-reverse/toolchain/binutils/objdump"
LINE = re.compile(r"^\s*([0-9a-f]+):\t([0-9a-f ]+)\t(\S+)\s*(.*)$")
NUM = re.compile(r"-?\b(?:0x[0-9a-fA-F]+|\d+)\b")


def disasm_file(path, base, tag):
    """反汇编整个文件，返回 [(abs_addr, mnemonic, operands)] 与其文本流。"""
    out = f"/tmp/sd_{tag}.asm"
    if not os.path.exists(out):
        subprocess.run([OBJDUMP, "-D", "-b", "binary", "-m", "mn10300",
                        "--insn-width=16", f"--adjust-vma=0x{base:X}", path],
                       stdout=open(out, "w"), stderr=subprocess.DEVNULL)
    return out


def build_streams(asm_path, lo, hi, shape_path, full_path):
    """把 [lo,hi) 地址范围的指令写成 shape/full 两条流。"""
    nshape = nfull = 0
    with open(asm_path, errors="replace") as f, \
         open(shape_path, "w") as fs, open(full_path, "w") as ff:
        for line in f:
            m = LINE.match(line)
            if not m:
                continue
            addr = int(m.group(1), 16)
            if addr < lo or addr >= hi:
                continue
            mn = m.group(3).strip()
            ops = m.group(4).strip()
            fs.write(mn + " " + NUM.sub("#", ops) + "\n")
            ff.write(mn + " " + ops + "\n")
            nshape += 1
            nfull += 1
    return nshape


def run_diff(a, b, tag):
    out = f"/tmp/sd_{tag}.diff"
    with open(out, "w") as o:
        subprocess.run(["diff", "-U0", "--color=never", a, b], stdout=o,
                       stderr=subprocess.DEVNULL)
    return out


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_hunks(diff_path):
    """返回 [(a_start0,a_count,b_start0,b_count)]，0-based。"""
    out = []
    with open(diff_path, errors="replace") as f:
        for line in f:
            m = HUNK.match(line)
            if m:
                a0 = int(m.group(1)); ac = int(m.group(2) or 1)
                b0 = int(m.group(3)); bc = int(m.group(4) or 1)
                if ac == 0: a0 -= 1
                if bc == 0: b0 -= 1
                out.append((a0, ac, b0, bc))
    return out


def covered(hunks, total):
    """把 hunk 区间合成覆盖标记。"""
    mask = bytearray(total + 1)
    for a0, ac, b0, bc in hunks:
        for i in range(b0, min(b0 + bc, total)):
            mask[i] = 1
    return mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("base")
    ap.add_argument("--lo", default=None); ap.add_argument("--hi", default=None)
    ap.add_argument("--work", default="/tmp/semdiff")
    ap.add_argument("--dump", default="/tmp/semdiff_numeric_only.txt")
    args = ap.parse_args()

    base = int(args.base, 0)
    os.makedirs(args.work, exist_ok=True)
    ta = hashlib.sha1(os.path.abspath(args.a).encode()).hexdigest()[:8]
    tb = hashlib.sha1(os.path.abspath(args.b).encode()).hexdigest()[:8]

    la = os.path.getsize(args.a)
    lo = int(args.lo, 0) if args.lo else 0
    hi = int(args.hi, 0) if args.hi else la
    alo, blo = base + lo, base + hi
    print(f"区间：file 0x{lo:X}..0x{hi:X}   runtime 0x{alo:X}..0x{blo:X}")

    asm_a = disasm_file(args.a, base, ta)
    asm_b = disasm_file(args.b, base, tb)

    sa = f"{args.work}/shape_A.txt"; fa = f"{args.work}/full_A.txt"
    sb = f"{args.work}/shape_B.txt"; fb = f"{args.work}/full_B.txt"
    if all(os.path.exists(x) and os.path.getsize(x) > 0 for x in (sa, fa, sb, fb)):
        print("复用已生成的指令流 …")
        nA = sum(1 for _ in open(sa)); nB = sum(1 for _ in open(sb))
    else:
        print("生成 A 流 …", flush=True); nA = build_streams(asm_a, alo, blo, sa, fa)
        print("生成 B 流 …", flush=True); nB = build_streams(asm_b, alo, blo, sb, fb)
    print(f"指令条数  A={nA}  B={nB}  (Δ={nB-nA})")

    print("diff shape …", flush=True); ds = run_diff(sa, sb, "shape")
    print("diff full  …", flush=True); df = run_diff(fa, fb, "full")

    hs = parse_hunks(ds); hf = parse_hunks(df)
    ns = sum(h[1] for h in hs); ns2 = sum(h[3] for h in hs)
    nf = sum(h[1] for h in hf); nf2 = sum(h[3] for h in hf)
    print(f"\nshape diff：{len(hs)} hunk，A侧 {ns} 行 / B侧 {ns2} 行  "
          f"→ 骨架变化 {max(ns,ns2)*100/max(nA,1):.3f}%")
    print(f"full  diff：{len(hf)} hunk，A侧 {nf} 行 / B侧 {nf2} 行  "
          f"→ 数值变化 {max(nf,nf2)*100/max(nA,1):.3f}%")

    ms = covered(hs, max(nA, nB)); mf = covered(hf, max(nA, nB))
    numeric_only = sum(1 for i in range(max(nA, nB)) if mf[i] and not ms[i])
    struct = sum(1 for i in range(max(nA, nB)) if ms[i])
    print(f"\n结构性改动行（shape 也变了）：{struct}")
    print(f"纯数值改动行（shape 未变，只有数字变了）：{numeric_only}"
          f"  ({numeric_only*100/max(nA,1):.3f}%)")

    # 列出结构性改动 hunk
    print("\n--- 结构性改动 hunk（shape 变化）---")
    with open(fa) as f1, open(fb) as f2:
        la_ = f1.readlines(); lb_ = f2.readlines()
    for a0, ac, b0, bc in hs[:60]:
        print(f"  A#{a0}({ac}行) B#{b0}({bc}行)")
        for i in range(a0, min(a0 + ac, len(la_))):
            print(f"    - {la_[i].rstrip()}")
        for i in range(b0, min(b0 + bc, len(lb_))):
            print(f"    + {lb_[i].rstrip()}")

    # 抽取纯数值改动的行对，解析数字 delta
    print("\n--- 纯数值改动的数字 delta 统计 ---")
    deltas = collections.Counter()
    samples = collections.defaultdict(list)
    for i in range(min(len(la_), len(lb_))):
        if not mf[i] or ms[i]:
            continue
        if la_[i] == lb_[i]:
            continue
        na = [int(x, 0) for x in NUM.findall(la_[i])]
        nb = [int(x, 0) for x in NUM.findall(lb_[i])]
        if len(na) != len(nb):
            continue
        for x, y in zip(na, nb):
            d = y - x
            deltas[d] += 1
            if len(samples[d]) < 4:
                samples[d].append((la_[i].rstrip(), lb_[i].rstrip()))
    for d, c in deltas.most_common(25):
        print(f"  delta {d:>+12} : {c:>7} 次")
        for x, y in samples[d][:2]:
            print(f"      - {x}")
            print(f"      + {y}")

    with open(args.dump, "w") as o:
        for a0, ac, b0, bc in hf:
            for i in range(a0, min(a0 + ac, len(la_))):
                o.write(f"- {la_[i].rstrip()}\n")
            for i in range(b0, min(b0 + bc, len(lb_))):
                o.write(f"+ {lb_[i].rstrip()}\n")
            o.write("\n")
    print(f"\n数值改动明细 → {args.dump}")


if __name__ == '__main__':
    main()
