#!/usr/bin/env python3
"""CRC/hash semantics under byte-order and bit-order transforms."""
import hashlib
import struct
import zlib
import numpy as np

P = "/home/sanyu/Projects/work/E-P5_固件_1.8/OLY_E_108_1800_0000_0000.BIN"
data = open(P, "rb").read()
PARTS = [(0x00000000, 0x00F00000), (0x00F00000, 0x024E0000),
         (0x024E0000, 0x02740000), (0x02740000, 0x02AC0000)]

BITREV = np.array([int(f"{i:08b}"[::-1], 2) for i in range(256)], dtype=np.uint8)


def transforms(buf: bytes):
    a = np.frombuffer(buf, dtype=np.uint8)
    out = {
        "identity": buf,
        "rev_bytes": buf[::-1],
        "swap16": bytes(np.frombuffer(buf, dtype="<u2").byteswap()),
        "bitrev_each": BITREV[a].tobytes(),
        "not_each": bytes((~a).astype(np.uint8)),
        "nib_swap": bytes(((a >> 4) | ((a & 0x0F) << 4)).astype(np.uint8)),
    }
    return out


print("=" * 88)
print("CRC32 / HASH under transforms, per partition")
print("=" * 88)
for i, (s, e) in enumerate(PARTS):
    part = data[s:e]
    want = struct.unpack("<I", part[-4:])[0]
    want_be = struct.unpack(">I", part[-4:])[0]
    pay = part[0x20:-0x20]
    print(f"\n### part{i}  want_le=0x{want:08X} want_be=0x{want_be:08X}")
    hits = []
    for rname, rng in [("payload", pay), ("part", part), ("part[:-0x20]", part[:-0x20])]:
        for tname, tb in transforms(rng).items():
            c = zlib.crc32(tb) & 0xFFFFFFFF
            if c == want:
                hits.append(f"crc32({tname} of {rname})")
            if struct.unpack(">I", struct.pack("<I", c))[0] == want:
                hits.append(f"crc32({tname} of {rname}) byteswapped")
            if c == want_be:
                hits.append(f"crc32({tname} of {rname}) ==BE")
            for hname, h in [("md5", hashlib.md5), ("sha1", hashlib.sha1),
                             ("sha256", hashlib.sha256)]:
                d = h(tb).digest()
                if struct.unpack("<I", d[:4])[0] == want:
                    hits.append(f"{hname}({tname} of {rname})[:4] LE")
                if struct.unpack(">I", d[:4])[0] == want:
                    hits.append(f"{hname}({tname} of {rname})[:4] BE")
                if struct.unpack("<I", d[-4:])[0] == want:
                    hits.append(f"{hname}({tname} of {rname})[-4:] LE")
                if struct.unpack(">I", d[-4:])[0] == want:
                    hits.append(f"{hname}({tname} of {rname})[-4:] BE")
    print("   ", hits if hits else "no match")

print("\n" + "=" * 88)
print("SEED SOLVE: find CRC32 init such that crc32(payload, seed) == want")
print("  (affine solve over GF(2))")
print("=" * 88)


def solve_seed(buf, want):
    n = len(buf)
    base = zlib.crc32(buf, 0) & 0xFFFFFFFF
    target = (want ^ base) & 0xFFFFFFFF
    z = b"\x00" * n
    zbase = zlib.crc32(z, 0) & 0xFFFFFFFF
    cols = []
    for j in range(32):
        v = zlib.crc32(z, 1 << j) & 0xFFFFFFFF
        cols.append((v ^ zbase) & 0xFFFFFFFF)
    # solve sum_j x_j * cols[j] == target over GF(2)
    rows = []
    for bit in range(32):
        rows.append(sum(((cols[j] >> bit) & 1) << j for j in range(32)))
    rhs = [(target >> bit) & 1 for bit in range(32)]
    # gaussian elimination
    mat = [[rows[i], rhs[i]] for i in range(32)]
    piv = []
    r = 0
    for c in range(32):
        pr = next((k for k in range(r, 32) if (mat[k][0] >> c) & 1), None)
        if pr is None:
            continue
        mat[r], mat[pr] = mat[pr], mat[r]
        for k in range(32):
            if k != r and (mat[k][0] >> c) & 1:
                mat[k][0] ^= mat[r][0]
                mat[k][1] ^= mat[r][1]
        piv.append(c)
        r += 1
        if r == 32:
            break
    if r < 32:
        return None, "singular"
    sol = 0
    for i, c in enumerate(piv):
        if mat[i][1]:
            sol |= 1 << c
    return sol, "solved"


for i, (s, e) in enumerate(PARTS):
    part = data[s:e]
    want = struct.unpack("<I", part[-4:])[0]
    pay = part[0x20:-0x20]
    seed, st = solve_seed(pay, want)
    if seed is None:
        print(f"  part{i}: {st}")
        continue
    chk = zlib.crc32(pay, seed) & 0xFFFFFFFF
    print(f"  part{i}: seed=0x{seed:08X}  verify crc32(payload,seed)=0x{chk:08X} want=0x{want:08X} "
          f"{'OK' if chk == want else 'FAIL'}")
