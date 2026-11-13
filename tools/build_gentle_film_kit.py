"""Package gentle_sepia (浓郁色调) film firmwares into flashable ZIP kits.

Each look occupies the Gentle Sepia ART slot (photo mode 91), which has NO vignette
and NO blur — only a warm sepia base tint, so it suits warm film looks. Reuses the
RC2-verified chroma-curve mechanism; each firmware must pass verify_gentle.py and
verify_gentle_route.py before flashing. Includes the official 1.8 recovery ZIP.
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
from tools.build_gentle_film import build_gentle_firmware, SIZE, CARD_FILE
from tools.build_native_film_pack import look_by_key, LOOKS

# Warm looks suit the sepia base tint; cool/high-saturation looks get muddied.
WARM_LOOKS = ["gold200", "portra160"]

# Short ART labels (<=6 UTF-16 units) for the gentle_sepia menu entry.
LABELS = {
    "gold200": ("柯达金200", "柯達金200"),
    "portra160": ("人像160", "人像160"),
    "velvia50": ("浓艳50", "濃豔50"),
    "classicchrome": ("经典铬", "經典鉻"),
    "ektar100": ("风景100", "風景100"),
    "bleach": ("银留漂白", "銀留漂白"),
    "moriyama_bw": ("森山黑白", "森山黑白"),
    "trix_bw": ("Tri-X", "Tri-X"),
}


def write_archive(path, firmware, digest, note):
    if len(firmware) != SIZE or hashlib.sha256(firmware).hexdigest() != digest:
        raise ValueError(f"refusing to package unexpected firmware: {path.name}")
    contents = {CARD_FILE: firmware,
                "SHA256SUMS": f"{digest}  {CARD_FILE}\n".encode("ascii"),
                "READ-ME.txt": note.encode("utf-8")}
    with ZipFile(path, "x") as archive:
        for name, value in contents.items():
            info = ZipInfo(name); info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, value, compress_type=ZIP_DEFLATED)
    with ZipFile(path) as archive:
        if archive.namelist() != list(contents) or any(
                archive.read(n) != v for n, v in contents.items()):
            raise ValueError(f"ZIP read-back differs: {path.name}")


def gentle_note(look, digest):
    lines = ["Olympus PEN E-P5 1.8 — 胶片风格包（浓郁色调槽，无暗角）",
             "机制：已在一台 E-P5 验证启动/全尺寸成片/官方恢复的 RC2 色度曲线补丁，",
             "改挂到浓郁色调（gentle_sepia）槽。经原生写入器与完整拍摄路径探针校验：",
             "仅浓郁色调变色，录像与其他模式保持原厂。",
             "",
             "重要：浓郁色调槽本身带一层暖褐 sepia 底色（无暗角、无模糊）。",
             "因此适合暖调胶片（柯达金/Portra）；冷调或高饱和风格会被底色染脏。",
             "这些曲线尚未在相机实拍；取景预览与最终 JPEG 一致性需上机对照。",
             "",
             f"风格：{look.name_zh}（{look.key}）— {look.note}",
             "", f"固件：{CARD_FILE}（{SIZE:,} 字节）",
             f"本候选 SHA-256：{digest}",
             f"官方 1.8 恢复原包 SHA-256：{STOCK_SHA256}（同目录恢复包）",
             "拍照：ART → 浓郁色调效果；4:3、最大尺寸、RAW+JPEG。",
             "关闭效果：切回 P/A/S/M 的 Natural。色度曲线不做色相旋转/亮度S曲线/颗粒。",
             "安装前备份照片，先拍原厂浓郁色调与 Natural 对照；阅读 docs/SD_TRIAL.txt。"]
    return "\n".join(lines) + "\n"


def build_kit(stock_path, dest, keys):
    if dest.exists():
        raise FileExistsError(f"Output already exists: {dest}")
    stock = stock_path.read_bytes()
    check_stock(stock)
    install = (ROOT / "docs/SD_TRIAL.txt").read_text(encoding="utf-8")
    recovery = ("Olympus PEN E-P5 1.8 — 原厂恢复包（不含任何胶片风格）\n"
                f"{CARD_FILE}，{SIZE:,} 字节，SHA-256：{STOCK_SHA256}\n"
                "此包恢复原厂 1.8。仅在机身仍可进入 SD 更新入口时使用。请用另一张备份卡。\n\n")
    dest.parent.mkdir(parents=True, exist_ok=True)
    rec_name = "E-P5-1.8-STOCK-RECOVERY.zip"
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp)
        names = []
        for key in keys:
            look = look_by_key(key)
            zh, zht = LABELS.get(key, (look.name_zh[:6], look.name_zh[:6]))
            fw = build_gentle_firmware(stock, look, label_zh=zh, label_zht=zht)
            digest = hashlib.sha256(fw).hexdigest()
            name = f"E-P5-1.8-Gentle-{key}.zip"
            write_archive(stage / name, fw, digest, gentle_note(look, digest) + "\n" + install)
            names.append(name)
        write_archive(stage / rec_name, stock, STOCK_SHA256, recovery + install)
        names.append(rec_name)
        with ExitStack() as rollback:
            dest.mkdir(); rollback.callback(dest.rmdir)
            for name in names:
                (stage / name).rename(dest / name)
                rollback.callback((dest / name).unlink)
            rollback.pop_all()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--looks", nargs="*", default=WARM_LOOKS,
                   help="look keys (default: warm looks suited to sepia base)")
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    build_kit(args.stock, args.out, args.looks)
    for path in sorted(args.out.glob("*.zip")):
        print(path)


if __name__ == "__main__":
    main()
