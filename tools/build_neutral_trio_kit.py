"""Package the neutralized trio (no vignette) into a flashable ZIP kit.
Includes official 1.8 recovery. Every archive re-opened and compared byte-for-byte."""
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
from tools.build_neutral_trio import build_neutral_trio, SIZE, CARD_FILE
from tools.build_native_film_pack import look_by_key


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


def trio_note(looks, digest):
    lines = ["Olympus PEN E-P5 1.8 — 胶片风格三槽包（无暗角·中性化）",
             "",
             "★ 本包已去除针孔暗角和所有空间效果 ★",
             "机制：RC2 色度曲线补丁 + 效果函数中性化（MOV 指针清零）。",
             "ISP 只做中性 RAW→YC 显影，色度曲线在 JPEG 编码前注入胶片色彩。",
             "RAW (ORF) 完全不受影响。全幅 4608×3456，一次 JPEG 压缩。",
             "",
             "经原生写入器 + 完整拍摄路径探针校验（3槽×3录像状态=9组全过）：",
             "仅针孔 I/II/III 色度变化，效果函数已清零，录像与其他模式原厂。",
             "这些曲线尚未在相机实拍；取景预览与最终 JPEG 一致性需上机对照。",
             "",
             "三个风格（ART → 针孔相机，按右方向键切换 I/II/III）："]
    for slot in ("I", "II", "III"):
        key = looks.get(slot)
        if key:
            look = look_by_key(key)
            lines.append(f"  针孔 {slot}：{look.name_zh}（{key}）— {look.note}")
        else:
            lines.append(f"  针孔 {slot}：原厂")
    lines += ["", f"固件：{CARD_FILE}（{SIZE:,} 字节）",
              f"本候选 SHA-256：{digest}",
              f"官方 1.8 恢复原包 SHA-256：{STOCK_SHA256}（同目录恢复包）",
              "",
              "拍照：ART → 针孔相机 → 右键选 I/II/III；4:3、最大尺寸、RAW+JPEG。",
              "关闭效果：切回 P/A/S/M 的 Natural。",
              "",
              "能力边界：色度曲线表达饱和/微偏色/去色。",
              "不能：色相旋转、亮度S曲线、颗粒、暗角（已去除）。",
              "黑白风格为纯去色，高反差请用机身对比度设置补足。",
              "",
              "安装前备份照片；阅读 docs/SD_TRIAL.txt 的刷入与恢复说明。",
              "参考：Canon M-Film / Soup Engine 的卡上换风格体验是下一步目标。"]
    return "\n".join(lines) + "\n"


def build_kit(stock_path, dest, looks):
    if dest.exists():
        raise FileExistsError(f"Output already exists: {dest}")
    stock = stock_path.read_bytes()
    check_stock(stock)
    install = (ROOT / "docs/SD_TRIAL.txt").read_text(encoding="utf-8")
    fw = build_neutral_trio(stock, looks)
    digest = hashlib.sha256(fw).hexdigest()
    recovery = ("Olympus PEN E-P5 1.8 — 原厂恢复包（不含任何胶片风格）\n"
                f"{CARD_FILE}，{SIZE:,} 字节，SHA-256：{STOCK_SHA256}\n"
                "此包恢复原厂 1.8。仅在机身仍可进入 SD 更新入口时使用。请用另一张备份卡。\n\n")
    dest.parent.mkdir(parents=True, exist_ok=True)
    trio_name = "E-P5-1.8-Film-Neutral-TRIO.zip"
    rec_name = "E-P5-1.8-STOCK-RECOVERY.zip"
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp)
        write_archive(stage / trio_name, fw, digest, trio_note(looks, digest) + "\n" + install)
        write_archive(stage / rec_name, stock, STOCK_SHA256, recovery + install)
        with ExitStack() as rollback:
            dest.mkdir(); rollback.callback(dest.rmdir)
            for name in (trio_name, rec_name):
                (stage / name).rename(dest / name)
                rollback.callback((dest / name).unlink)
            rollback.pop_all()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--i", required=True)
    p.add_argument("--ii", required=True)
    p.add_argument("--iii", required=True)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    looks = {"I": args.i, "II": args.ii, "III": args.iii}
    build_kit(args.stock, args.out, looks)
    for path in sorted(args.out.glob("*.zip")):
        print(path)


if __name__ == "__main__":
    main()
