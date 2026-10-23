#!/usr/bin/env python3
"""E-P5 艺术滤镜子系统分析工具（三合一）。

子命令
------
callers    用自建的 CALL 编码规则全块反查某地址的调用点
           （MN10300: CALL = `cd` + u32，低 16 位是有符号位移，高字节是参数/帧大小；
             Ghidra 的引用分析在本工程不完整，必须自己扫）
registry   列出块 0 里所有具 ID 的滤镜实现与 MODE_EXPOSE_* 曝光预设
patterns   校验补丁配方里每个 find 模式在块 0 的命中数

用法
----
python tools/art_subsystem_scan.py callers  --block <块0 decoded.bin> --addr 0x40788616
python tools/art_subsystem_scan.py registry --block <块0 decoded.bin>
python tools/art_subsystem_scan.py patterns --block <块0 decoded.bin> --patterns fcad94eb2a60,...
"""
import argparse
import re
import struct
from collections import defaultdict
from pathlib import Path

BASE = 0x402C0000  # 块 0 基址：Ghidra 运行地址 = 块内文件偏移 + 块基址


def scan_callers(d, targets):
    out = defaultdict(list)
    for i in range(len(d) - 5):
        if d[i] != 0xCD:
            continue
        imm = struct.unpack_from("<I", d, i + 1)[0]
        disp = imm & 0xFFFF
        if disp & 0x8000:
            disp -= 0x10000
        tgt = (BASE + i) + disp
        if tgt in targets:
            out[tgt].append(BASE + i)
    return out


def cmd_callers(a, d):
    targets = {int(x, 0) for x in a.addr}
    res = scan_callers(d, targets)
    for t in sorted(targets):
        lst = res.get(t, [])
        print("%#010x  callers=%d  %s" % (t, len(lst), [hex(x) for x in lst[:20]]))


def cmd_registry(a, d):
    impl = defaultdict(list)
    expose = defaultdict(list)
    for m in re.finditer(rb"[\x20-\x7e]{6,}", d):
        t = m.group().decode("latin-1")
        mm = re.fullmatch(r"art_(effect|filter)_(\d+)_([a-z0-9_]+)", t)
        if mm:
            impl[int(mm.group(2))].append((mm.group(1), mm.group(3), BASE + m.start()))
        mm = re.fullmatch(r"MODE_EXPOSE_([A-Z0-9_]+)", t)
        if mm:
            expose[mm.group(1)].append((BASE + m.start(), t))
    print("=== 具 ID 的滤镜实现（%d 个）===" % len(impl))
    for num in sorted(impl):
        for kind, nm, addr in impl[num]:
            print("  ID %3d  %-7s %-22s @ %#010x" % (num, kind, nm, addr))
    print("\n=== MODE_EXPOSE_* 曝光预设（%d 套，每套含 _MOVIE 版）===" % len(expose))
    for k in sorted(expose):
        for addr, t in expose[k]:
            print("  %-44s @ %#010x" % (t, addr))


def cmd_patterns(a, d):
    for hx in a.patterns:
        p = bytes.fromhex(hx)
        n = d.count(p)
        locs = []
        i = d.find(p)
        while i != -1:
            locs.append(BASE + i)
            i = d.find(p, i + 1)
        print("%-24s hits=%d  %s" % (hx, n, [hex(x) for x in locs[:8]]))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["callers", "registry", "patterns"])
    ap.add_argument("--block", required=True, type=Path, help="块 0 decoded.bin")
    ap.add_argument("--addr", nargs="*", default=[])
    ap.add_argument("--patterns", nargs="*", default=[])
    a = ap.parse_args()
    d = a.block.read_bytes()
    if a.cmd == "callers":
        cmd_callers(a, d)
    elif a.cmd == "registry":
        cmd_registry(a, d)
    else:
        cmd_patterns(a, d)


if __name__ == "__main__":
    main()
