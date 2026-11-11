#!/usr/bin/env python3
"""Prepare separate E-P5 RC2 and stock recovery ZIPs on the computer."""
import argparse
from contextlib import ExitStack
import hashlib
from pathlib import Path
import sys
import tempfile
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_native_film import CANDIDATE_SHA256, build_film, package_note
from tools.inspect_ep5 import STOCK_SHA256, check_stock

CARD_FILE = "DCOLYMP/E1089999.BIN"
SIZE = 44_826_624
CANDIDATE_ZIP = "E-P5-1.8-Soft-Chrome-RC2-TRIAL.zip"
STOCK_ZIP = "E-P5-1.8-STOCK-RECOVERY.zip"


def write_archive(path, firmware, digest, note):
    if len(firmware) != SIZE or hashlib.sha256(firmware).hexdigest() != digest:
        raise ValueError(f"refusing to package unexpected firmware: {path.name}")
    contents = {
        CARD_FILE: firmware,
        "SHA256SUMS": f"{digest}  {CARD_FILE}\n".encode("ascii"),
        "READ-ME.txt": note.encode("utf-8"),
    }
    with ZipFile(path, "x") as archive:
        for name, value in contents.items():
            # Stable filenames, timestamps, permissions and ordering.
            info = ZipInfo(name)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, value, compress_type=ZIP_DEFLATED)
    with ZipFile(path) as archive:
        if archive.namelist() != list(contents) or any(
                archive.read(name) != value for name, value in contents.items()):
            raise ValueError(f"ZIP read-back differs: {path.name}")


def build_kit(source, dest):
    if dest.exists():
        raise FileExistsError(f"Output already exists: {dest}")
    with source.open("rb") as stream:
        stock = stream.read(SIZE + 1)
    check_stock(stock)
    candidate = build_film(stock, revision=2)
    install = (ROOT / "docs/SD_TRIAL.txt").read_text(encoding="utf-8")
    recovery = (
        "Olympus PEN E-P5 1.8 — 原厂恢复包（没有柔彩）\n"
        f"{CARD_FILE}，{SIZE:,} 字节，SHA-256：{STOCK_SHA256}\n"
        "此包会恢复原厂 1.8，不能恢复以前安装的第三方改动或个人设置。\n"
        "只在机身仍可进入 SD 更新入口时使用。请用另一张备份卡，勿与候选包混放。\n\n"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp)
        write_archive(stage / CANDIDATE_ZIP, candidate, CANDIDATE_SHA256[2],
                      package_note(2, CANDIDATE_SHA256[2]) + "\n" + install)
        write_archive(stage / STOCK_ZIP, stock, STOCK_SHA256, recovery + install)
        # Only publish after both archives have been verified. Never replace a kit.
        with ExitStack() as rollback:
            dest.mkdir()
            rollback.callback(dest.rmdir)
            for name in (CANDIDATE_ZIP, STOCK_ZIP):
                (stage / name).rename(dest / name)
                rollback.callback((dest / name).unlink)
            rollback.pop_all()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("--out", required=True, type=Path, help="new local directory")
    args = parser.parse_args()
    try:
        build_kit(args.stock, args.out)
    except (OSError, ValueError, BadZipFile) as exc:
        parser.exit(1, f"{exc}\n")
    for name in (CANDIDATE_ZIP, STOCK_ZIP):
        print(args.out / name)


if __name__ == "__main__":
    main()
