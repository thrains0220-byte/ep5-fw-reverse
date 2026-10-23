#!/usr/bin/env python3
"""kind 0x106 分区跨机型/跨版本清单：数据区定位、符号集、熵、SHA-256 分组、两两差分。
用途：证明六比特 blob 在 2012–2017 各机型上逐字节恒定。
用法: blk106_inventory.py <decoded 目录>...
"""
import sys, os, glob, struct, collections, hashlib

def find_data(d):
    """定位 6-bit 数据区：头部 (len,addr) 之后跳过 0xFF 填充。"""
    ln, addr = struct.unpack_from('<II', d, 0)
    i = 8
    while i < len(d) and d[i] == 0xFF:
        i += 1
    return ln, addr, i

def analyze(path):
    d = open(path, 'rb').read()
    ln, addr, off = find_data(d)
    data = d[off:off + ln]
    hist = collections.Counter(data)
    mx = max(data) if data else 0
    missing = [i for i in range(64) if i not in hist]
    h = -sum((c/len(data))*__import__('math').log2(c/len(data)) for c in hist.values()) if data else 0
    return dict(path=path, size=len(d), ln=ln, addr=addr, off=off,
                ndata=len(data), ndist=len(hist), mx=mx, missing=missing,
                ent=h, sha=hashlib.sha256(data).hexdigest(),
                hist=hist, data=data)

files = []
for root in sys.argv[1:]:
    files.extend(sorted(glob.glob(os.path.join(root, '**', '02_0106_*.decoded.bin'), recursive=True)))

res = [analyze(f) for f in files]
print(f"{'file':<62} {'size':>9} {'len':>8} {'off':>5} {'ndist':>5} {'max':>4} {'ent':>6} {'missing':<10} sha256[:12]")
for r in res:
    print(f"{os.path.relpath(r['path']):<62} {r['size']:>9} {r['ln']:>8X} {r['off']:>5} {r['ndist']:>5} {r['mx']:>4} {r['ent']:>6.3f} {str(r['missing']):<10} {r['sha'][:12]}")

# 相同 sha 分组
print("\n== 内容分组（sha256） ==")
g = collections.defaultdict(list)
for r in res:
    g[r['sha']].append(os.path.relpath(r['path']))
for sha, lst in g.items():
    print(f"  {sha[:12]}  x{len(lst)}")
    for x in lst:
        print(f"      {x}")

# 差分（同一对之间的字节差异）
print("\n== 两两差分（按长度取公共前缀，逐字节比） ==")
for i in range(len(res)):
    for j in range(i+1, len(res)):
        a, b = res[i]['data'], res[j]['data']
        n = min(len(a), len(b))
        if a[:n] == b[:n]:
            print(f"  {os.path.basename(os.path.dirname(res[i]['path'])):>28} vs {os.path.basename(os.path.dirname(res[j]['path'])):>28}: 前 {n} 字节完全相同")
            continue
        # 首个差异
        k = 0
        while k < n and a[k] == b[k]:
            k += 1
        diff = sum(1 for t in range(n) if a[t] != b[t])
        print(f"  {os.path.basename(os.path.dirname(res[i]['path'])):>28} vs {os.path.basename(os.path.dirname(res[j]['path'])):>28}: 长度 {len(a)}/{len(b)} 首差@0x{k:X} 差异字节 {diff}/{n} ({diff/n*100:.2f}%)")
