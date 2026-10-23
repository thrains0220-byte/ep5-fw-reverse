#!/usr/bin/env python3
"""mask ROM dump 到位后，一条命令解掉所有判据问题。

背景（第 22–23 轮）:
    E-P5 v1.8 的艺术滤镜 / AF 判据全部落在**机身 mask ROM** 里，
    `.BIN` 里只有引用。已确认 mask ROM **不由任何固件映像承载**、
    **也不随官方更新下发**（41 组请求字段变体全部只返回 1 个 `.BIN`）。
    => 唯一剩下的入口 = **实机 dump**。

本脚本:
    读入一份 mask ROM 镜像（裸二进制），按运行地址索引，
    然后把「第 22 轮 mask ROM 依赖清单 R1–R12」逐条读出来并解释：
      R1/R2  照片 / 录像侧菜单描述符（4 字节结构：{首资源ID, 项数} 的两个假设都试）
      R3     52 项 × 4 字节的描述符族
      R4/R5  拍照 / 录像效果参数源
      R6     类型 1（拍照）/ 类型 2（录像）装载源
      R7     9–10 个效果参数块
      R8     16 槽「子 ID → 处理函数」分派表
      R9     录像参数源
      R10    AF 参数表 + 错误串
      R11    6 项 {u32 ID, u32 ptr} 参数表（并跟随指针读出参数数组）

用法:
    python tools/rom_fill_report.py --rom maskrom.bin --rom-base 0x7E000000
    python tools/rom_fill_report.py --rom maskrom.bin --json report.json
    # 只看某几条：
    python tools/rom_fill_report.py --rom maskrom.bin --only R1 R2 R11
"""
import argparse
import hashlib
import json
import struct

# ---- 第 22 轮的 mask ROM 依赖清单（E-P5 v1.8）----
R1 = 0x7E452BDC          # 照片侧菜单描述符
R2 = 0x7E452BE4          # 录像侧菜单描述符
R3_BASE, R3_N = 0x7E452B30, 52   # 描述符族
R4 = 0x7E5C9809          # 拍照效果参数源
R5 = 0x7E5C9B1C          # 录像效果参数源
R6A, R6B = 0x7E5C9D1E, 0x7E5C9E0E   # 类型 1 / 类型 2 装载源
R7 = [0x7E5C913E, 0x7E5C9142, 0x7E5C9146, 0x7E5C9169, 0x7E5C916D,
      0x7E5C9171, 0x7E5C9185, 0x7E5C918A, 0x7E5C918F, 0x7E5C9194]
R8 = 0x7E897CF4          # 16 槽 × 8 B 分派表
R9 = 0x7E8973D0          # 录像参数源
R10_TAB = 0x7E503C78     # AF 参数表
R10_STR = [0x7E503C87, 0x7E503CA5, 0x7E503CC6]   # 错误串
R10_OUT = [0x7E503CE3, 0x7E503CF2]               # 输出表
R11 = 0x7E429774          # 6 项 {u32 ID, u32 ptr}
R12 = 0x7E429540          # 另一处 ID 查表


class Rom:
    def __init__(self, data, base):
        self.d = data
        self.base = base

    def off(self, addr):
        return addr - self.base

    def ok(self, addr, n=1):
        o = self.off(addr)
        return 0 <= o and o + n <= len(self.d)

    def raw(self, addr, n):
        o = self.off(addr)
        if o < 0 or o + n > len(self.d):
            return None
        return self.d[o:o + n]

    def u8(self, a):
        b = self.raw(a, 1)
        return None if b is None else b[0]

    def u16(self, a):
        b = self.raw(a, 2)
        return None if b is None else struct.unpack("<H", b)[0]

    def u32(self, a):
        b = self.raw(a, 4)
        return None if b is None else struct.unpack("<I", b)[0]

    def cstr(self, a, maxn=128):
        b = self.raw(a, maxn)
        if b is None:
            return None
        i = b.find(b"\x00")
        return b[:i if i >= 0 else maxn].decode("latin-1", "replace")


def hexdump(raw, width=16, maxlines=16):
    if raw is None:
        return "  (超出 dump 范围)"
    out = []
    for i in range(0, min(len(raw), width * maxlines), width):
        chunk = raw[i:i + width]
        out.append("  %04X  %-*s  %s" % (
            i, width * 3, " ".join("%02x" % b for b in chunk),
            "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)))
    if len(raw) > width * maxlines:
        out.append("  ... (共 %d 字节)" % len(raw))
    return "\n".join(out)


def desc4(rom, addr):
    """4 字节描述符的两种解释：
       A: {u16 首资源ID, u16 项数}
       B: {u32 打包值}
    """
    a = rom.u16(addr)
    b = rom.u16(addr + 2)
    v = rom.u32(addr)
    return ("A:{首ID=0x%04X(%s) 项数=%d}   B:0x%08X"
            % (a, _res_id(a), b, v))


def _res_id(v):
    """把 16 位值按 ASCII 资源 ID 风格解出来（如 0x4133 -> 'A13'）。"""
    s = "".join(chr(c) if 32 <= c < 127 else "." for c in (v >> 8, v & 0xFF))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True)
    ap.add_argument("--rom-base", type=lambda x: int(x, 0), default=0x7E000000)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    data = open(args.rom, "rb").read()
    rom = Rom(data, args.rom_base)
    print("ROM dump : %s" % args.rom)
    print("大小     : %d 字节 (%.2f MB)" % (len(data), len(data) / 1048576.0))
    print("基址     : 0x%08X  → 覆盖 0x%08X .. 0x%08X"
          % (args.rom_base, args.rom_base, args.rom_base + len(data) - 1))
    print("SHA-256  : %s" % hashlib.sha256(data).hexdigest())
    print()

    want = set(args.only) if args.only else None

    def on(tag):
        return want is None or tag in want

    rep = {"sha256": hashlib.sha256(data).hexdigest(),
           "base": args.rom_base, "size": len(data), "items": {}}

    if on("R1") or on("R2"):
        print("=" * 72)
        print("R1 / R2 —— 照片 / 录像侧菜单描述符（★ 最关键：10 项 vs 4 项就在这 8 字节）")
        for tag, addr in (("R1(照片)", R1), ("R2(录像)", R2)):
            idx = (addr - R3_BASE) // 4
            in_fam = (addr - R3_BASE) % 4 == 0 and 0 <= idx < R3_N
            print("  %s @ 0x%08X%s" % (
                tag, addr,
                ("  [= R3 族第 %d 项]" % idx) if in_fam else ""))
            print("    " + desc4(rom, addr))
            raw = rom.raw(addr, 4)
            print(hexdump(raw))
            rep["items"].setdefault(tag, {})["addr"] = addr
            rep["items"][tag]["family_index"] = idx if in_fam else None
            rep["items"][tag]["raw"] = raw.hex() if raw else None
        print("  ★ 判据：若 R1 解析出 {首ID=A03x(照片第1项), 项数=10} =>")
        print("        录像侧改读同一张表即可得 10 项（1 字节类型码补丁成立）。")
        print("        若 R2 解析出 {首ID=A04x, 项数=4} 且与 R1 无关 => ROM 侧无可借清单。")
        print()

    if on("R3"):
        print("=" * 72)
        print("R3 —— 52 项 × 4 字节描述符族 @ 0x%08X" % R3_BASE)
        fam = []
        for i in range(R3_N):
            a = R3_BASE + 4 * i
            raw = rom.raw(a, 4)
            if raw is None:
                print("  [%2d] 0x%08X  (超出范围)" % (i, a))
                continue
            print("  [%2d] 0x%08X  %s" % (i, a, desc4(rom, a)))
            fam.append({"idx": i, "addr": a, "raw": raw.hex()})
        rep["items"]["R3"] = fam
        print()

    if on("R4") or on("R5") or on("R6"):
        print("=" * 72)
        print("R4 / R5 / R6 —— 效果参数源与装载源")
        for tag, addr, n in (("R4(拍照参数源)", R4, 96),
                             ("R5(录像参数源)", R5, 96),
                             ("R6A(类型1装载源)", R6A, 48),
                             ("R6B(类型2装载源)", R6B, 48)):
            raw = rom.raw(addr, n)
            print("  %s @ 0x%08X" % (tag, addr))
            print(hexdump(raw, maxlines=8))
            rep["items"].setdefault(tag, {})["addr"] = addr
        print()

    if on("R7"):
        print("=" * 72)
        print("R7 —— 9–10 个效果参数块（每个 64 字节 u16 预览）")
        for a in R7:
            print("  0x%08X" % a)
            print(hexdump(rom.raw(a, 64), maxlines=4))
        print()

    if on("R8"):
        print("=" * 72)
        print("R8 —— 16 槽 × 8 字节「子 ID → 处理函数」分派表 @ 0x%08X" % R8)
        for i in range(16):
            a = R8 + 8 * i
            lo, hi = rom.u32(a), rom.u32(a + 4)
            print("  槽 %2d  0x%08X : id=0x%08X  handler=0x%08X" % (i, a, lo, hi))
        print()

    if on("R9"):
        print("=" * 72)
        print("R9 —— 录像参数源 @ 0x%08X" % R9)
        print(hexdump(rom.raw(R9, 96), maxlines=6))
        print()

    if on("R10"):
        print("=" * 72)
        print("R10 —— AF 参数表与错误串")
        print("  AF 参数表 @ 0x%08X" % R10_TAB)
        print(hexdump(rom.raw(R10_TAB, 64), maxlines=4))
        for a in R10_STR:
            print("  串 @ 0x%08X : %r" % (a, rom.cstr(a)))
        for a in R10_OUT:
            print("  输出表 @ 0x%08X" % a)
            print(hexdump(rom.raw(a, 32), maxlines=2))
        print()

    if on("R11") or on("R12"):
        print("=" * 72)
        print("R11 / R12 —— {u32 ID, u32 ptr} 参数表")
        for tag, addr in (("R11", R11), ("R12", R12)):
            print("  %s @ 0x%08X" % (tag, addr))
            for i in range(6):
                a = addr + 8 * i
                rid, ptr = rom.u32(a), rom.u32(a + 4)
                print("    项 %d  0x%08X  ID=0x%08X  ptr=0x%08X" % (i, a, rid, ptr))
                if ptr and rom.ok(ptr, 32):
                    print("        参数数组前 32 字节:")
                    print(hexdump(rom.raw(ptr, 32), maxlines=2, ))
        print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print("[written] %s" % args.json)


if __name__ == "__main__":
    main()
