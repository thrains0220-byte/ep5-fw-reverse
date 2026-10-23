#!/usr/bin/env python3
"""在 MN103 代码块中定位「镜头 ID 表」：8 字节记录 {cat:u16, idx:u16, maker:u8, model:u8, pad:u16=0}。
用法: find_lens_table.py <block0.bin> [base]
"""
import sys, collections

def find_runs(d, base):
    runs = []
    i = 0
    n = len(d)
    while i + 8 <= n:
        cat = d[i] | (d[i+1] << 8)
        idx = d[i+2] | (d[i+3] << 8)
        maker, model = d[i+4], d[i+5]
        pad = d[i+6] | (d[i+7] << 8)
        if pad == 0 and cat <= 15 and maker != 0 and model != 0 and idx < 0x10000:
            j = i
            cnt = 0
            while j + 8 <= n:
                c2 = d[j] | (d[j+1] << 8)
                m2, mo2 = d[j+4], d[j+5]
                p2 = d[j+6] | (d[j+7] << 8)
                if p2 == 0 and c2 <= 15 and m2 != 0 and mo2 != 0:
                    j += 8; cnt += 1
                else:
                    break
            if cnt >= 8:
                runs.append((i, cnt))
                i = j
                continue
        i += 8
    return runs

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
d = open(path, 'rb').read()
runs = find_runs(d, base)
print(f"{path}  size={len(d)}")
for off, cnt in runs:
    print(f"\n== 表 @ 偏移 0x{off:X} (base 0x{base:08X} -> 0x{base+off:08X})  {cnt} 条")
    recs = []
    for k in range(cnt):
        o = off + k*8
        recs.append((base+o, d[o]|(d[o+1]<<8), d[o+2]|(d[o+3]<<8), d[o+4], d[o+5]))
    makers = collections.Counter(r[3] for r in recs)
    print("   厂商码分布:", ' '.join(f'{k:02X}:{v}' for k, v in sorted(makers.items())))
    for r in recs:
        print(f"     0x{r[0]:08X} cat={r[1]:2d} idx=0x{r[2]:04X} lensID={r[3]:02X}:{r[4]:02X}")
