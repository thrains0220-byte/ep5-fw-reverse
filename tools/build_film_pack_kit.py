"""Package native film looks into flashable ZIPs with the official recovery ZIP.

Each look ZIP contains DCOLYMP/E1089999.BIN (44,826,624 bytes), SHA256SUMS and a
READ-ME. The official 1.8 recovery ZIP is included once. Every archive is written
then re-opened and compared byte-for-byte before publication, mirroring the
verified RC2 trial-kit flow. No SD write, no camera connection.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.inspect_ep5 import STOCK_SHA256, check_stock
from tools.build_native_film_pack import build_look_firmware, look_by_key, SIZE, CARD_FILE
from tools.native_film_curves import LOOKS, look_tables

LABELS = {
    "gold200": ("柯达金200", "柯達金200"),
    "portra160": ("人像160", "人像160"),
    "velvia50": ("浓艳反转50", "濃豔反轉50"),
    "classicchrome": ("经典铬", "經典鉻"),
    "ektar100": ("风景100", "風景100"),
    "bleach": ("漂白银留", "漂白銀留"),
    "moriyama_bw": ("森山黑白", "森山黑白"),
    "trix_bw": ("TriX黑白", "TriX黑白"),
}


def write_archive(path: Path, firmware: bytes, digest: str, note: str) -> None:
    if len(firmware) != SIZE or hashlib.sha256(firmware).hexdigest() != digest:
        raise ValueError(f"refusing to package unexpected firmware: {path.name}")
    contents = {
        CARD_FILE: firmware,
        "SHA256SUMS": f"{digest}  {CARD_FILE}\n".encode("ascii"),
        "READ-ME.txt": note.encode("utf-8"),
    }
    with ZipFile(path, "x") as archive:
        for name, value in contents.items():
            info = ZipInfo(name)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, value, compress_type=ZIP_DEFLATED)
    with ZipFile(path) as archive:
        if archive.namelist() != list(contents) or any(
                archive.read(name) != value for name, value in contents.items()):
            raise ValueError(f"ZIP read-back differs: {path.name}")


def look_note(look, digest: str) -> str:
    rep = look_tables(look)
    cerr = max(rep["chroma_error"]["cb_max"], rep["chroma_error"]["cr_max"])
    return (
        f"Olympus PEN E-P5 1.8 — 胶片风格 {look.name_zh}（{look.key}）\n"
        f"机制：已在一台 E-P5 验证启动/全尺寸成片/官方恢复的 RC2 色度曲线补丁。\n"
        f"本候选只改针孔 I 的两条色度曲线，录像与其他模式保持原厂；无新增代码。\n"
        f"这些曲线尚未在相机实拍验证；色度近似最大误差 {cerr:.1f}/255。\n"
        f"{look.note}\n"
        f"固件：{CARD_FILE}（{SIZE:,} 字节）\n"
        f"本候选 SHA-256：{digest}\n"
        f"官方 1.8 恢复原包 SHA-256：{STOCK_SHA256}（同目录恢复包）\n"
        f"拍照：ART → 针孔（菜单显示「{LABELS[look.key][0]}」）→ I；4:3、最大尺寸、RAW+JPEG。\n"
        f"关闭效果：切回 P/A/S/M 的 Natural。黑白风格的高反差/颗粒不在色度曲线范围。\n"
        f"安装前备份卡上照片，先拍原厂针孔 I 与 Natural 对照；阅读 docs/SD_TRIAL.txt。\n"
    )


def build_kit(stock_path: Path, dest: Path, keys: list[str]) -> None:
    if dest.exists():
        raise FileExistsError(f"Output already exists: {dest}")
    stock = stock_path.read_bytes()
    check_stock(stock)
    install = (ROOT / "docs/SD_TRIAL.txt").read_text(encoding="utf-8")
    recovery = (
        "Olympus PEN E-P5 1.8 — 原厂恢复包（不含任何胶片风格）\n"
        f"{CARD_FILE}，{SIZE:,} 字节，SHA-256：{STOCK_SHA256}\n"
        "此包恢复原厂 1.8，不恢复第三方改动或个人设置。仅在机身仍可进入 SD 更新入口时使用。\n"
        "请用另一张备份卡，勿与候选包混放。\n\n"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    names = []
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp)
        for key in keys:
            look = look_by_key(key)
            zh, zht = LABELS[key]
            fw = build_look_firmware(stock, look, label_zh=zh, label_zht=zht)
            digest = hashlib.sha256(fw).hexdigest()
            name = f"E-P5-1.8-Film-{key}.zip"
            write_archive(stage / name, fw, digest, look_note(look, digest) + "\n" + install)
            names.append(name)
        rec_name = "E-P5-1.8-STOCK-RECOVERY.zip"
        write_archive(stage / rec_name, stock, STOCK_SHA256, recovery + install)
        names.append(rec_name)
        with ExitStack() as rollback:
            dest.mkdir()
            rollback.callback(dest.rmdir)
            for name in names:
                (stage / name).rename(dest / name)
                rollback.callback((dest / name).unlink)
            rollback.pop_all()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--looks", nargs="*", default=[l.key for l in LOOKS],
                        help="look keys to package (default: all)")
    args = parser.parse_args(argv)
    build_kit(args.stock, args.out, args.looks)
    for p in sorted(args.out.glob("*.zip")):
        print(p)


if __name__ == "__main__":
    main()
