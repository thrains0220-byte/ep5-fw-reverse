#!/usr/bin/env python3
"""按**字节模式**给任意一版 Olympus .BIN 打补丁并重新打包成可刷固件。

为什么按模式而不是按偏移
------------------------
实机相机的固件版本可能与分析用的 v1.8 不同，块 0 布局会变。
因此补丁描述成「在块 0 里找到唯一的字节序列 X，改成 Y」，对任何版本都成立；
命中数不等于期望值就**直接拒绝**，绝不猜。

配方 JSON
---------
    {
      "name": "...",
      "expect_source_sha256": "....",          // 可选
      "blocks": [
        {"block_index": 0,
         "patches": [
           {"name": "...", "find": "27cc06", "replace": "27ffff",
            "expect_hits": 1, "note": "..."}
         ]}
      ]
    }

用法:
    python tools/make_patched_firmware.py --image OLY_E_108_1800_0000_0000.BIN \
        --recipe patches/ep5_af_stepcap.json --out patched.BIN
    python tools/make_patched_firmware.py --image ... --recipe ... --dry-run
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oly_container as oc  # noqa: E402


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--recipe", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args()

    recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
    data = args.image.read_bytes()

    print("原固件 : %s" % args.image)
    print("大小   : %d" % len(data))
    print("SHA256 : %s" % sha256(data))
    exp = recipe.get("expect_source_sha256")
    if exp and exp.lower() != sha256(data):
        print("!! 配方指定的原固件 SHA-256 不匹配，拒绝继续")
        return 2
    print("配方   : %s" % recipe.get("name", args.recipe.name))
    print()

    blocks = oc.parse(data)
    if oc.reconstruct(blocks) != data:
        print("!! decode/encode 未能逐字节复现原文件，拒绝继续")
        return 2
    print("[OK] 容器往返逐字节一致（解码/再编码 == 原文件）")
    print()

    by_idx = {b.index: b for b in blocks}
    new_blocks = list(blocks)
    report = {"source": str(args.image), "source_sha256": sha256(data),
              "recipe": str(args.recipe), "recipe_name": recipe.get("name"),
              "patches": []}
    ok = True

    for bs in recipe.get("blocks", []):
        idx = bs["block_index"]
        blk = by_idx.get(idx)
        if blk is None:
            print("!! 配方引用了不存在的块 %d" % idx)
            ok = False
            continue
        payload = bytearray(blk.payload)
        for p in bs.get("patches", []):
            find = bytes.fromhex(p["find"])
            repl = bytes.fromhex(p["replace"])
            if len(find) != len(repl):
                print("  [%s] 拒绝：长度不等（%d -> %d），本工具只做等长覆盖"
                      % (p["name"], len(find), len(repl)))
                ok = False
                continue
            hits = []
            i = 0
            while True:
                j = payload.find(find, i)
                if j < 0:
                    break
                hits.append(j)
                i = j + 1
            want = p.get("expect_hits", 1)
            applied = (len(hits) == want and want > 0)
            print("  %-24s 命中 %d 处（期望 %d） %s"
                  % (p["name"], len(hits), want, "OK" if applied else "!! 拒绝修改"))
            print("       find   : %s" % find.hex(" "))
            print("       replace: %s" % repl.hex(" "))
            if p.get("note"):
                print("       note   : %s" % p["note"])
            for h in hits:
                print("       @payload 0x%08X   runtime 0x%08X   container 0x%08X"
                      % (h, blk.address + h, blk.address + 32 + h))
            if not applied:
                ok = False
            else:
                for h in hits:
                    payload[h:h + len(find)] = repl
            report["patches"].append({
                "block_index": idx, "name": p["name"],
                "find": p["find"], "replace": p["replace"],
                "hits": len(hits), "applied": applied,
                "offsets": [hex(h) for h in hits],
            })
        # 用工具自带的 replace_payload 重算该块的加性校验和
        new_blocks[idx] = oc.replace_payload(blk, bytes(payload))

    print()
    if not ok:
        print("=> 有补丁未安全命中，未生成输出。")
        return 2

    out = oc.reconstruct(new_blocks)
    # 自检：重新解析输出，校验块头/校验和仍然自洽
    back = oc.parse(out)
    print("[自检] 重新解析输出：%d 个块，全部块校验和自洽" % len(back))
    print("新固件 SHA-256: %s" % sha256(out))
    print("新固件大小     : %d" % len(out))
    report["output_sha256"] = sha256(out)
    report["output_size"] = len(out)

    if args.dry_run:
        print("=> 试运行完成，未写文件。")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(out)
        print("=> 已写出 %s" % args.out)
    if args.report:
        args.report.write_text(json.dumps(report, indent=1, ensure_ascii=False),
                               encoding="utf-8")
        print("=> 报告 %s" % args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
