#!/usr/bin/env python3
"""对已解码的块 0 做定点字节补丁，并给出前后 SHA-256 校验。

用途（第 21 轮）:
    把社区改机补丁「模式 A」的语义等价物落到 E-P5 v1.8 块 0：
      1) 解除 AF 驱动步数上限   —— 改写 `MOV #imm16, A3` 的两个上限常量
      2) 解除镜头 ID 白名单校验 —— 删除「表尾哨兵 → 未识别」那条分支

安全性:
    * 只在**已解码**的块 0 上工作（`decoded/*.decoded.bin`），不碰原始 `.BIN`；
    * 补丁前先校验「期望原字节」，不符即拒绝；
    * 输出 before/after SHA-256，可逆（记录了原始字节）。

用法:
    # 试运行（只报告，不写文件）
    python tools/apply_block_patch.py --blk0 decoded/00_0100_402c0020.decoded.bin --recipe patches/ep5_v1_8_af_unlock.json

    # 实际写入（需要 --write）
    python tools/apply_block_patch.py --blk0 decoded/00_0100_402c0020.decoded.bin \
        --recipe patches/ep5_v1_8_af_unlock.json --write --out patched/00_0100_402c0020.decoded.bin
"""
import argparse
import hashlib
import json
import os
import shutil


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.recipe, encoding="utf-8") as f:
        rec = json.load(f)

    data = bytearray(open(args.blk0, "rb").read())
    print("块 0 : %s  (%d 字节)" % (args.blk0, len(data)))
    print("配方 : %s" % args.recipe)
    print("before SHA-256 : %s" % sha256(data))
    print()

    ok = True
    for p in rec["patches"]:
        off = int(p["offset"], 0)
        expect = bytes.fromhex(p["expect"])
        new = bytes.fromhex(p["replace"])
        got = bytes(data[off:off + len(expect)])
        match = (got == expect)
        ok = ok and match
        print("  %-14s off 0x%08X  %s" % (p["name"], off,
              "OK" if match else "MISMATCH"))
        print("      expect  : %s" % expect.hex(" "))
        print("      actual  : %s" % got.hex(" "))
        print("      replace : %s   %s" % (new.hex(" "), p.get("note", "")))
        if not match:
            print("      !! 原字节不符，拒绝补丁")
    print()

    if not ok:
        print("=> 校验失败，未做任何修改。")
        return 2

    for p in rec["patches"]:
        off = int(p["offset"], 0)
        data[off:off + len(bytes.fromhex(p["replace"]))] = bytes.fromhex(p["replace"])

    print("after  SHA-256 : %s" % sha256(data))
    if not args.write:
        print("=> 试运行完成（未写文件）。加 --write 才会落盘。")
        return 0

    out = args.out or (args.blk0 + ".patched")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)
    print("=> 已写入 %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
