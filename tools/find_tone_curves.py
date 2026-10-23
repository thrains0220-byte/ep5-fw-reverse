#!/usr/bin/env python3
"""用「参考机型的色调曲线」特征字节，去别的固件块里搜同一张表。

起因:
    E-M10 II v1.4 的 `kind 0x106` 资源容器里发现 **10 个等长 41,472 B 的
    色调/对比度曲线表**（32 B 零头 + u16 递增带平台的曲线），
    而 E-P5 v1.8 的 0x106 分区只有 6-bit blob、没有资源目录。
    ⇒ 关键问题：**E-P5 里有没有等价的曲线表？**
    若有 ⇒ 艺术滤镜的「创作数据」在 .BIN 内可改 ⇒ 目标①（新增滤镜）有路。
    若无 ⇒ 曲线只存在于 mask ROM ⇒ 目标① 只能走「参数变体」。

用法:
    python tools/find_tone_curves.py --ref <参考0x106.bin> --ref-base 0x43160000 \
        --ref-idx 30 --targets <块文件>[:基址] ...
"""
import argparse
import os
import struct


def load_ref(path, base, idx, count=40):
    d = open(path, "rb").read()
    # 先找目录
    for off in range(0, len(d) - count * 16, 4):
        ok = True
        for k in range(count):
            a, s, z1, z2 = struct.unpack_from("<4I", d, off + k * 16)
            if z1 or z2 or s == 0 or s > 4 << 20 or not (base <= a < base + 0x2000000):
                ok = False
                break
        if ok:
            a, s, _, _ = struct.unpack_from("<4I", d, off + idx * 16)
            return d[a - base:a - base + s]
    return None


def curve_signature(b, n=64):
    """取 32 B 零头之后的 n 字节作为特征。"""
    return b[32:32 + n]


def find_ramps(d, min_len=1024):
    """在数据里找「32 B 零头 + u16 递增带平台」的曲线表。"""
    out = []
    n = len(d)
    i = 0
    while i + 64 < n:
        if d[i:i + 32] == b"\x00" * 32:
            v = struct.unpack_from("<%dH" % min(32, (n - i - 32) // 2), d, i + 32)
            if all(v[j] <= v[j + 1] + 8 for j in range(len(v) - 1)) and v[-1] > 0:
                # 延伸到末尾
                j = i + 32
                last = v[-1]
                while j + 2 <= n:
                    cur = struct.unpack_from("<H", d, j)[0]
                    if cur > last + 8 or cur == 0:
                        break
                    last = cur
                    j += 2
                if j - (i + 32) >= min_len:
                    out.append((i, j - (i + 32)))
                    i = j
                    continue
        i += 2
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="参考 0x106 分区文件")
    ap.add_argument("--ref-base", default="0x43160000")
    ap.add_argument("--ref-idx", type=int, default=30)
    ap.add_argument("--targets", nargs="+", required=True,
                    help="目标块文件，格式 path[:base]")
    args = ap.parse_args()

    ref = load_ref(args.ref, int(args.ref_base, 0), args.ref_idx)
    if not ref:
        print("参考曲线未定位")
        return
    sig = curve_signature(ref)
    print("参考曲线: len=%d  特征 64B = %s" % (len(ref), sig.hex(" ")))
    print("  u16 前 12 = %s\n" % (struct.unpack_from("<12H", ref, 32),))

    for t in args.targets:
        path, _, bstr = t.rpartition(":")
        base = int(bstr, 0) if bstr else 0
        d = open(path, "rb").read()
        n = d.count(sig)
        ramps = find_ramps(d)
        print("目标 %-52s 特征命中 %d 处 | 曲线型候选 %d 个 %s" % (
            os.path.basename(path)[:52], n, len(ramps),
            [(hex(o), l) for o, l in ramps[:6]]))
        if n:
            i = 0
            shown = 0
            while shown < 6:
                j = d.find(sig, i)
                if j < 0:
                    break
                print("      命中 @ file 0x%08X (rt 0x%08X)" % (j, base + j))
                i = j + 1
                shown += 1
        print()


if __name__ == "__main__":
    main()
