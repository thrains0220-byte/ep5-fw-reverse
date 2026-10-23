#!/usr/bin/env python3
"""把两版块 0 的差异字节按「所属指令字段」分类，回答：差异到底是重链接还是真改动。

做法
----
1. 用 objdump 反汇编两版，得到 每条指令的 (偏移, 长度, 助记符, 操作数)。
2. 对每个差异字节，按 A 侧覆盖它的指令分类：
     * IMM32   —— 落在 `fc <op> <imm32>` 6 字节指令的立即数字段（绝对地址/大常量）
     * RELOC   —— 落在 call / bra / b<cc> 等相对转移指令的偏移字段
     * OPCODE  —— 落在助记符/寄存器字段
     * IMM8/16 —— 落在 8/16 位立即数字段
     * DATA    —— 落在非指令区域（数据表 / 字符串）
3. 汇总占比。

用法: diff_field_classify.py <A.bin> <B.bin> <base_hex> [objdump]
"""
import sys, re, subprocess, collections, os

OBJDUMP = sys.argv[4] if len(sys.argv) > 4 else \
    "/home/sanyu/Projects/work/ep5-fw-reverse/toolchain/binutils/objdump"
LINE = re.compile(r"^\s*([0-9a-f]+):\t([0-9a-f ]+)\t(\S+)\s*(.*)$")
BRANCH = re.compile(r"^(b|bra|beq|bne|bge|bgt|ble|blt|bcs|bcc|bls|bhi|blo|dbra|dbra|"
                    r"call|jmp|rcall|movm|push|pop)", re.I)

import hashlib

def _tag(path):
    """basename 会碰撞（v1.3/v1.4 同名），用路径 hash 区分缓存文件。"""
    h = hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:10]
    return f"{os.path.basename(path)}_{h}"

def disasm(path, base, cache):
    out = f"/tmp/dc_{_tag(path)}.asm"
    if not os.path.exists(out):
        subprocess.run([OBJDUMP, "-D", "-b", "binary", "-m", "mn10300", "--insn-width=16",
                        f"--adjust-vma=0x{base:X}", path],
                       stdout=open(out, "w"), stderr=subprocess.DEVNULL)
    return out

def parse(path, base):
    out = f"/tmp/dc_{_tag(path)}.asm"
    if not os.path.exists(out):
        subprocess.run([OBJDUMP, "-D", "-b", "binary", "-m", "mn10300", "--insn-width=16",
                        f"--adjust-vma=0x{base:X}", path],
                       stdout=open(out, "w"), stderr=subprocess.DEVNULL)
    import pickle
    pk = f"/tmp/dc_{_tag(path)}.pkl"
    if os.path.exists(pk):
        return pickle.load(open(pk, "rb"))
    ins = {}
    for line in open(out, errors="replace"):
        m = LINE.match(line)
        if not m:
            continue
        off = int(m.group(1), 16)
        raw = bytes.fromhex(m.group(2).replace(" ", ""))
        mn = m.group(3).strip()
        ops = m.group(4).strip()
        ins[off] = (len(raw), mn, ops, raw)
    pickle.dump(ins, open(pk, "wb"), protocol=4)
    return ins

def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    base = int(sys.argv[3], 0)
    A = open(a_path, 'rb').read()
    B = open(b_path, 'rb').read()
    print("反汇编 A …", flush=True); IA = parse(a_path, base)
    print("反汇编 B …", flush=True); IB = parse(b_path, base)
    print(f"A 指令 {len(IA)}   B 指令 {len(IB)}\n")

    # 覆盖表：offset -> (kind, instr_off)
    def cover(ins, base):
        """objdump 打印绝对地址（= 文件偏移 + base），覆盖表必须用文件偏移。"""
        c = {}
        for abs_off, (ln, mn, ops, raw) in ins.items():
            foff = abs_off - base
            for k in range(ln):
                c[foff + k] = (foff, mn, ops, raw, k, ln)
        return c

    CA = cover(IA, base)
    cls = collections.Counter()
    total = 0
    for i in range(min(len(A), len(B))):
        if A[i] == B[i]:
            continue
        total += 1
        ent = CA.get(i)
        if ent is None:
            cls['DATA(非指令区)'] += 1
            continue
        off, mn, ops, raw, k, ln = ent
        if raw[:1] == b'\xfc' and ln == 6 and k >= 2:
            cls['IMM32(6字节 fc 立即数=绝对地址/常量)'] += 1
        elif BRANCH.match(mn):
            cls[f'RELOC({mn})'] += 1
        elif ln <= 2:
            cls['OPCODE/立即数8位'] += 1
        else:
            cls[f'OTHER({mn})'] += 1
    print(f"差异字节合计：{total}\n")
    for k, v in cls.most_common():
        print(f"  {v:>9}  ({v*100//max(total,1):>3}%)  {k}")

if __name__ == '__main__':
    main()
