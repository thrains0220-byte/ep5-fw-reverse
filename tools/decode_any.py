#!/usr/bin/env python3
"""解混淆任意奥林巴斯固件（容器格式与机型无关），输出各块与清单。

用法: decode_any.py <固件.BIN> <输出目录>
"""
import json
import subprocess
import sys
from pathlib import Path

TOOL = "/home/sanyu/Projects/work/ep5-fw-reverse/tools/oly_container.py"


def main():
    img = Path(sys.argv[1])
    out = Path(sys.argv[2])
    if out.exists():
        print(f"输出目录已存在: {out}")
        sys.exit(1)
    out.mkdir(parents=True)
    dec = out / "decoded"
    r = subprocess.run([sys.executable, TOOL, str(img), "--out", str(dec)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        sys.exit(r.returncode)
    rep = json.loads(r.stdout)
    print(f"源文件: {img}  {rep['source_size']} B  sha256={rep['source_sha256'][:16]}…")
    print(f"往返一致: {rep['roundtrip_identical']}")
    for b in rep["blocks"]:
        print(f"  块{b['index']}  kind={b['kind']}  flags={b['kind']}  "
              f"addr={b['header_address']}  size={b['payload_size']:>9}  "
              f"sha256={b['decoded_sha256'][:16]}…  {b['decoded_file']}")


if __name__ == "__main__":
    main()
