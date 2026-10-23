#!/usr/bin/env python3
"""指令级严格判定：两版固件代码块的差异，是「地址重定位」还是「真实语义改动」。

这是本项目最关键的一次判定。已知 E-PM2 v1.5→v1.6、E-M5 v2.2→v2.3
**就是 2018-12-18 松下 H-ES200/H-ES50200 AF 修复的那一对**，
因此这两对的分析结果具有「地面真值」意义。

方法
----
1. objdump 反汇编两版（按指令边界，而非字节扫描）。
2. 两条指令流按**下标一一配对**（若指令条数不等则说明有增删，单独报告）。
3. 对每一对配对指令：
     * 助记符不同        → 结构性改动
     * 操作数里的数字不同 → 逐个分类：
         - 地址型（0x40000000–0x7FFFFFFF，代码/数据/RAM 地址空间）
         - 常量型（其余，含 ±小整数、位掩码、查表下标）
4. 指令覆盖不到的区域 = 数据区，直接逐字节比对并列出差异区间。

用法: semantic_pair_diff.py A.bin B.bin BASE [--objdump PATH] [--out JSON]
"""
import sys, os, re, json, hashlib, argparse, collections, subprocess, pickle

OBJDUMP_DEFAULT = "/home/sanyu/Projects/work/ep5-fw-reverse/toolchain/binutils/objdump"
LINE = re.compile(r"^\s*([0-9a-f]+):\t([0-9a-f ]+)\t(\S+)\s*(.*)$")
NUM = re.compile(r"-?\b(?:0x[0-9a-fA-F]+|\d+)\b")

ADDR_LO, ADDR_HI = 0x40000000, 0x80000000


def _tag(path):
    h = hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:10]
    return f"{os.path.basename(path)}_{h}"


def parse(path, base, objdump):
    """返回 [(abs_addr, length, mnemonic, operands_text, raw_bytes)]，带 pickle 缓存。"""
    pk = f"/tmp/spd_{_tag(path)}.pkl"
    if os.path.exists(pk):
        return pickle.load(open(pk, "rb"))
    asm = f"/tmp/spd_{_tag(path)}.asm"
    if not os.path.exists(asm):
        subprocess.run([objdump, "-D", "-b", "binary", "-m", "mn10300",
                        "--insn-width=16", f"--adjust-vma=0x{base:X}", path],
                       stdout=open(asm, "w"), stderr=subprocess.DEVNULL)
    ins = []
    for line in open(asm, errors="replace"):
        m = LINE.match(line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        raw = bytes.fromhex(m.group(2).replace(" ", ""))
        ins.append((addr, len(raw), m.group(3).strip(), m.group(4).strip(), raw))
    pickle.dump(ins, open(pk, "wb"), protocol=4)
    return ins


def nums(text):
    out = []
    for t in NUM.findall(text):
        try:
            out.append(int(t, 0))
        except ValueError:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("base")
    ap.add_argument("--objdump", default=OBJDUMP_DEFAULT)
    ap.add_argument("--out", default="/tmp/semantic_pair_diff.json")
    args = ap.parse_args()
    base = int(args.base, 0)

    A = open(args.a, 'rb').read()
    B = open(args.b, 'rb').read()
    print(f"A {args.a}  {len(A)} B")
    print(f"B {args.b}  {len(B)} B")
    print("反汇编 A …", flush=True); IA = parse(args.a, base, args.objdump)
    print("反汇编 B …", flush=True); IB = parse(args.b, base, args.objdump)
    print(f"指令条数 A={len(IA)}  B={len(IB)}  Δ={len(IB)-len(IA)}")

    # 按【偏移】配对：局部字段编辑模型下，指令边界基本不变，
    # 索引配对会被少量增删指令带偏，必须用地址对齐。
    Bmap = {}
    for addr, ln, ma, oa, ra in IB:
        Bmap[addr] = (ln, ma, oa, ra)
    Amap = {}
    for addr, ln, ma, oa, ra in IA:
        Amap[addr] = (ln, ma, oa, ra)

    paired = []            # (a_addr, a_entry, b_addr, b_entry)
    only_a = []
    for addr, ln, ma, oa, ra in IA:
        e = Bmap.get(addr)
        if e is None:
            only_a.append(addr)
        else:
            paired.append((addr, (ln, ma, oa, ra), e))
    only_b = [a for a in Bmap if a not in Amap]
    print(f"按偏移配对：成功 {len(paired)} 条；仅 A 有 {len(only_a)} 条；仅 B 有 {len(only_b)} 条")

    mn_diff = 0
    const_changes = []     # 常量型改动（真实语义改动的候选）
    addr_changes = []      # 地址型改动（重定位）
    struct = []            # 操作数个数变化

    for i, (aa, (la, ma, oa, ra), (lb, mb, ob, rb)) in enumerate(paired):
        if la != lb:
            struct.append({"idx": i, "a_addr": aa, "b_addr": aa,
                           "a": f"[{la}B] {ma} {oa}", "b": f"[{lb}B] {mb} {ob}",
                           "note": "指令长度不同"})
            continue
        if ma != mb:
            mn_diff += 1
            if len(struct) < 400:
                struct.append({"idx": i, "a_addr": aa, "b_addr": ab,
                               "a": f"{ma} {oa}", "b": f"{mb} {ob}"})
            continue
        na, nb = nums(oa), nums(ob)
        if len(na) != len(nb):
            struct.append({"idx": i, "a_addr": aa, "b_addr": ab,
                           "a": f"{ma} {oa}", "b": f"{mb} {ob}",
                           "note": "操作数个数不同"})
            continue
        for x, y in zip(na, nb):
            if x == y:
                continue
            is_addr = (ADDR_LO <= x < ADDR_HI) and (ADDR_LO <= y < ADDR_HI)
            rec = {"idx": i, "a_addr": aa, "b_addr": aa,
                   "a_mn": ma, "a_ops": oa, "b_mn": mb, "b_ops": ob,
                   "a_val": x, "b_val": y, "delta": y - x}
            if is_addr:
                addr_changes.append(rec)
            else:
                const_changes.append(rec)

    # ---- 数据区（两版都未被指令覆盖的字节）----
    cov = bytearray(len(A))
    for lst in (IA, IB):
        for addr, ln, ma, oa, ra in lst:
            off = addr - base
            for k in range(ln):
                if 0 <= off + k < len(cov):
                    cov[off + k] = 1
    data_diff = []
    i = 0
    while i < len(A):
        if A[i] != B[i] and not cov[i]:
            j = i
            while j < len(A) and A[j] != B[j] and not cov[j]:
                j += 1
            data_diff.append((i, j))
            i = j
        else:
            i += 1

    print(f"\n=== 指令级判定 ===")
    print(f"助记符不同（结构性）        : {mn_diff}")
    print(f"操作数个数不同（结构性）    : {len([s for s in struct if 'note' in s])}")
    print(f"地址型数字改动（重定位候选）: {len(addr_changes)}")
    print(f"常量型数字改动（语义候选）  : {len(const_changes)}")
    print(f"数据区差异区间              : {len(data_diff)}"
          f"（共 {sum(e-s for s,e in data_diff)} B）")

    if const_changes:
        print("\n--- 常量型改动明细（真实语义改动候选）---")
        for r in const_changes[:80]:
            print(f"  A#0x{r['a_addr']:08X}  {r['a_mn']} {r['a_ops']}")
            print(f"  B#0x{r['b_addr']:08X}  {r['b_mn']} {r['b_ops']}")
            print(f"      值 {r['a_val']} → {r['b_val']}   Δ={r['delta']}")
    if struct:
        print("\n--- 结构性改动明细（抽样）---")
        for r in struct[:40]:
            print(f"  A#0x{r['a_addr']:08X}  {r['a']}")
            print(f"  B#0x{r['b_addr']:08X}  {r['b']}")
    if data_diff:
        print("\n--- 数据区差异明细 ---")
        for s, e in data_diff[:40]:
            print(f"  0x{s:08X}..0x{e:08X} len={e-s}")
            print(f"    A: {A[s:min(e,s+32)].hex(' ')}")
            print(f"    B: {B[s:min(e,s+32)].hex(' ')}")

    # 地址型改动的 delta 分布（重定位一致性）
    dh = collections.Counter(r['delta'] for r in addr_changes)
    print(f"\n--- 地址型改动 delta 分布（Top 20，共 {len(dh)} 种）---")
    for d, c in dh.most_common(20):
        print(f"  Δ={d:>+12}  × {c}")

    json.dump({"a": args.a, "b": args.b, "base": hex(base),
               "instr_a": len(IA), "instr_b": len(IB),
               "paired_by_offset": len(paired),
               "only_a_instr": only_a[:200], "only_b_instr": sorted(only_b)[:200],
               "only_a_count": len(only_a), "only_b_count": len(only_b),
               "mnemonic_diff": mn_diff,
               "operand_count_diff": len([s for s in struct if 'note' in s]),
               "addr_field_changes": len(addr_changes),
               "const_field_changes": len(const_changes),
               "data_diff_intervals": len(data_diff),
               "data_diff_bytes": sum(e - s for s, e in data_diff),
               "const_changes": const_changes,
               "structural": struct[:400],
               "addr_delta_hist": [{"delta": d, "n": c} for d, c in dh.most_common(200)],
               "data_diffs": [{"a_start": s, "a_end": e, "len": e - s,
                               "a_head": A[s:min(e, s + 32)].hex(),
                               "b_head": B[s:min(e, s + 32)].hex()}
                              for s, e in data_diff]},
              open(args.out, "w"), indent=1)
    print(f"\n机读结果 → {args.out}")


if __name__ == '__main__':
    main()
