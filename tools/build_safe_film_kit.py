"""Package the SAFE 7-slot film firmware (effects preserved) into a flashable kit."""
from __future__ import annotations
import argparse, hashlib, sys, tempfile
from contextlib import ExitStack
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.inspect_ep5 import STOCK_SHA256, check_stock
from tools.build_safe_full import build_safe, SIZE, CARD_FILE


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
        if archive.namelist() != list(contents) or any(archive.read(n) != v for n, v in contents.items()):
            raise ValueError(f"ZIP read-back differs: {path.name}")


def safe_note(digest):
    lines = [
        "Olympus PEN E-P5 1.8 — 胶片色彩安全版（7槽·保留原厂效果·HQ 9节点）",
        "",
        "★ 本版保留原厂空间效果，只注入胶片色彩 ★",
        "机制：RC2 已真机验证的色度曲线补丁。不清零任何效果函数指针。",
        "ISP 完整运行原厂 RAW→YC + 原厂效果，色度曲线在 JPEG 编码前注入胶片色彩。",
        "RAW (ORF) 完全不受影响。全幅 4608×3456，一次 JPEG 压缩。",
        "录像/共享模式全部重路由到原厂恒等表（模式 72 锚点），保持原厂色彩。",
        "",
        "⚠ 与上一版（全量中性化）的区别：",
        "上一版清零了所有效果指针，导致 ART 取景黑屏、无法快门。",
        "本版保留原厂效果，机制与已成功上机的 RC2 完全相同。",
        "代价：针孔保留暗角，立体保留上下模糊，浓郁色调保留 sepia 底色。",
        "",
        "经原生写入器 + 完整拍摄路径探针校验（7槽×3录像状态=21组全过）：",
        "仅 7 个照片模式色度变化，效果函数全部保留，录像与其他 240+ 模式原厂。",
        "",
        "机内操作（ART 模式转盘）：",
        "  人像柔暖  → Portra 400（柔焦槽，原厂柔焦 + 暖人像色）",
        "  胶片色彩  → 按右方向键切换 I/II/III：",
        "    I   = Velvia 50（浓艳反转，原厂针孔暗角）",
        "    II  = Classic Chrome（经典铬，原厂针孔暗角）",
        "    III = Gold 200（暖金负片，原厂针孔暗角）",
        "  风景鲜艳  → Ektar 100（立体槽，原厂移轴模糊 + 鲜艳色）",
        "  电影色调  → CineStill 800T（浓郁色调槽，原厂 sepia + 电影色）",
        "  森山黑白  → Moriyama B&W（负片冲印槽，原厂交叉冲洗 + 去色）",
        "",
        "拍照：ART → 选上述任一 → 4:3、最大尺寸、RAW+JPEG。",
        "关闭效果：切回 P/A/S/M 的 Natural。",
        "",
        f"固件：{CARD_FILE}（{SIZE:,} 字节）",
        f"本候选 SHA-256：{digest}",
        f"官方 1.8 恢复原包 SHA-256：{STOCK_SHA256}（同目录恢复包）",
        "",
        "安装前备份照片；阅读 docs/SD_TRIAL.txt 的刷入与恢复说明。",
    ]
    return "\n".join(lines) + "\n"


def build_kit(stock_path, dest):
    if dest.exists():
        raise FileExistsError(f"Output already exists: {dest}")
    stock = stock_path.read_bytes()
    check_stock(stock)
    install = (ROOT / "docs/SD_TRIAL.txt").read_text(encoding="utf-8")
    fw = build_safe(stock)
    digest = hashlib.sha256(fw).hexdigest()
    recovery = ("Olympus PEN E-P5 1.8 — 原厂恢复包（不含任何胶片风格）\n"
                f"{CARD_FILE}，{SIZE:,} 字节，SHA-256：{STOCK_SHA256}\n"
                "此包恢复原厂 1.8。仅在机身仍可进入 SD 更新入口时使用。请用另一张备份卡。\n\n")
    dest.parent.mkdir(parents=True, exist_ok=True)
    safe_name = "E-P5-1.8-Film-SAFE-7.zip"
    rec_name = "E-P5-1.8-STOCK-RECOVERY.zip"
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp)
        write_archive(stage / safe_name, fw, digest, safe_note(digest) + "\n" + install)
        write_archive(stage / rec_name, stock, STOCK_SHA256, recovery + install)
        with ExitStack() as rollback:
            dest.mkdir(); rollback.callback(dest.rmdir)
            for name in (safe_name, rec_name):
                (stage / name).rename(dest / name)
                rollback.callback((dest / name).unlink)
            rollback.pop_all()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    build_kit(args.stock, args.out)
    for path in sorted(args.out.glob("*.zip")):
        print(path)


if __name__ == "__main__":
    main()
