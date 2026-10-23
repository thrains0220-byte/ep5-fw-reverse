#!/usr/bin/env python3
"""kind 0x106 资源容器：40 条 (运行地址,大小) 目录 → 逐资源 SHA-256 清单与版本间逐资源差分。
用法: res_diff.py <decoded_02_0106_*.bin> [<b> ...]
"""
import struct, sys, os, glob, hashlib

def resources(path):
    d = open(path, 'rb').read()
    i = d.find(b'OE')
    if i < 0:
        return None
    size = struct.unpack_from("<I", d, i+12)[0]
    payload = d[i+32:i+32+size]
    ents = []
    off = 0
    while off + 16 <= len(payload):
        a, s, x, y = struct.unpack_from('<IIII', payload, off)
        if not (0x40000000 <= a < 0x60000000) or not (0 < s <= 0x4000000) or x or y:
            break
        ents.append((a, s, off)); off += 16
    # 数据区紧随目录，按 (addr,size) 顺序对应
    out = []
    cur = off
    for k, (a, s, o) in enumerate(ents):
        blob = payload[cur:cur+s]
        cur += s
        out.append(dict(idx=k, addr=a, size=s, sha=hashlib.sha256(blob).hexdigest(),
                        head=blob[:8].hex(' '), maxb=max(blob) if blob else 0,
                        off=cur - s))
    return out

def show(path, res):
    name = os.path.basename(os.path.dirname(os.path.dirname(path)))
    print(f"\n=== {name}  ({len(res)} 个资源)")
    for r in res:
        print(f"  [{r['idx']:2d}] addr=0x{r['addr']:08X} size=0x{r['size']:>8X} max=0x{r['maxb']:02X} "
              f"sha={r['sha'][:12]} head={r['head']}")

pairs = [(sys.argv[1], sys.argv[2])] if len(sys.argv) >= 3 else []
for p in sys.argv[1:]:
    r = resources(p)
    if r:
        show(p, r)

if pairs:
    a, b = [resources(p) for p in pairs]
    print("\n=== 逐资源差分 ===")
    for ra, rb in zip(a, b):
        same = ra['sha'] == rb['sha']
        print(f"  [{ra['idx']:2d}] size {ra['size']:>8X}/{rb['size']:<8X} addr 0x{ra['addr']:08X}/0x{rb['addr']:08X} "
              f"{'相同' if same else '★不同'}  {ra['sha'][:10]} {rb['sha'][:10]}")
