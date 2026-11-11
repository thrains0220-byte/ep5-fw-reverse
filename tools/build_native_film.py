#!/usr/bin/env python3
"""Build the Soft Chrome native chroma-curve candidate for the Olympus E-P5 1.8."""
import argparse
from contextlib import ExitStack
import hashlib
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.film_update import build_update
from tools.inspect_ep5 import CPU_BASE, STOCK_SHA256


# Published full-container hashes of the reviewed recipes; never derive these
# from the image being packaged. A deliberately new recipe needs a new RC.
CANDIDATE_SHA256 = {
    1: "2f3eb6cd7d9b0c4bdd29414174e02fe850e26ed9dae482ad55a076559075243f",
    2: "90a63cd0b191f0d0cfdf344b2129723af07f6969d1d6368b8e2216a2019c1229",
}


def package_note(revision, digest):
    label = ("针孔相机效果（原厂名称）" if revision == 1 else
             "针孔/柔彩I（繁体：針孔/柔彩I，其他语言沿用原厂名称）")
    return (f"Olympus PEN E-P5 1.8 — 柔彩 Soft Chrome RC{revision}\n"
            "仅供 E-P5 实机试验。此版本尚未完成机身安装、成片和恢复验收。\n"
            "固件：DCOLYMP/E1089999.BIN（44,826,624 字节）\n"
            f"本候选 SHA-256：{digest}\n"
            f"官方 1.8 恢复原包 SHA-256：{STOCK_SHA256}（另行保存）\n"
            f"拍照：ART → {label} → I；4:3、最大尺寸、RAW+JPEG。\n"
            "关闭效果：切换回 P/A/S/M 的 Natural。此包内置一个风格，不导入 .cube。\n"
            "安装前先保存原厂针孔 I 和 Natural 对照；备份卡上的照片。\n"
            "试验前阅读仓库 docs/SOFT_CHROME.md 的 SD 更新、恢复及成片检查说明。\n")


def build_film(stock: bytes, *, revision: int = 2) -> bytes:
    if revision not in (1, 2):
        raise ValueError("unsupported Soft Chrome revision")
    # Two 49-byte native chroma tables. Slopes are Q7, with a leading slope
    # before the first knot and one after each knot, including padded knots.
    x = bytes([0] * 4 + [64, 128, 192] + [255] * 9)
    identity = x + x + bytes([0] * 4 + [128] * 4 + [0] * 9)
    y = bytes([40] * 4 + [74, 128, 182] + [215] * 9)
    curve = x + y + bytes([0] * 4 + [68, 108, 108, 67] + [0] * 9)
    edits = [(0x7e438bb0 - CPU_BASE, identity * 2, curve * 2)]
    # Movie mode 82 originally shares still 73's table. Case 0x7e22a01f
    # selects a second pair of byte-identical factory identity curves.
    # The CMIO initializer also copies every preset, regardless of active mode.
    for address, old, new in (
        (0x7e478ec4, 0x7e22a12f, 0x7e22a01f),
        (0x7e21d0e7, 0x7e438bc0, 0x7e438a38),
        (0x7e21d0fd, 0x7e438bd0, 0x7e438a48),
        (0x7e21d129, 0x7e438bf1, 0x7e438a69),
        (0x7e21d13f, 0x7e438c01, 0x7e438a79),
    ):
        edits.append((address - CPU_BASE, struct.pack("<I", old), struct.pack("<I", new)))
    language_edits = []
    if revision == 2:
        # String entries 69 and 602 in the Chinese TFT language packs.
        # Entry 1173 and the optional Pin Hole overlay describe other controls.
        for offset, prefix, old, new in (
            (0x2ce202, "", "针孔相机效果", "针孔/柔彩I"),
            (0x2d08ae, "@A045@", "针孔相机效果", "针孔/柔彩I"),
            (0x2db414, "", "針孔相機效果", "針孔/柔彩I"),
            (0x2ddaf8, "@A045@", "針孔相機效果", "針孔/柔彩I"),
        ):
            before = (prefix + old + "\0").encode("utf-16-le")
            after = (prefix + new + "\0").encode("utf-16-le")
            language_edits.append((offset, before, after))
    return build_update(stock, edits, language_edits=language_edits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path, help="original OLY_E_108_1800_0000_0000.BIN")
    parser.add_argument("--revision", type=int, choices=(1, 2), default=2,
                        help="2: Chinese ART menu (default), 1: original camera labels")
    parser.add_argument("--out", required=True, type=Path, help="new local output directory")
    args = parser.parse_args()
    folder = args.out
    if folder.exists():
        parser.exit(1, f"Output already exists: {folder}\n")
    try:
        with args.stock.open("rb") as source:
            candidate = build_film(source.read(44826624 + 1), revision=args.revision)
        digest = hashlib.sha256(candidate).hexdigest()
        if digest != CANDIDATE_SHA256[args.revision]:
            raise ValueError(f"RC{args.revision} firmware differs from the published SHA-256")
        dest = folder / "DCOLYMP" / "E1089999.BIN"
        folder.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder.parent) as directory:
            staged = Path(directory) / "candidate.part"
            staged.write_bytes(candidate)
            if hashlib.sha256(staged.read_bytes()).hexdigest() != digest:
                raise OSError("firmware read-back SHA-256 mismatch")
            # Reserve a new card folder and publish the firmware name last.
            with ExitStack() as rollback:
                folder.mkdir()
                rollback.callback(folder.rmdir)
                dest.parent.mkdir()
                rollback.callback(dest.parent.rmdir)
                for name, content in (
                    ("SHA256SUMS", f"{digest}  DCOLYMP/E1089999.BIN\n".encode("ascii")),
                    ("READ-ME.txt", package_note(args.revision, digest).encode("utf-8")),
                ):
                    note = Path(directory) / name
                    note.write_bytes(content)
                    note.rename(folder / name)
                    rollback.callback((folder / name).unlink)
                staged.replace(dest)
                rollback.pop_all()
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(f"{digest}  {dest}")


if __name__ == "__main__":
    main()
