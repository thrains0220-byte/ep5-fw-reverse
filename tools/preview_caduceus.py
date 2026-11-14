"""Render a side-by-side preview: safe-7 curves vs new Caduceus curves.

Applies each look's Cb/Cr pair curves to a neutral base photo in the BT.601
chroma plane (the same transform the E-P5 ISP pair performs). This is a
chroma-only approximation for judging colour character before flashing; it
does not model the factory spatial effects (vignette/blur) or tone tables.

Usage:
  python tools/preview_caduceus.py base.jpg --out build/caduceus-fit/preview.png
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from native_film_curves_hq import HQ_LOOKS, build_hq_table

def rgb_to_ycbcr(rgb):
    r, g, b = rgb[..., 0] * 255, rgb[..., 1] * 255, rgb[..., 2] * 255
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    return y, cb, cr

def ycbcr_to_rgb(y, cb, cr):
    dcb, dcr = cb - 128, cr - 128
    r = y + 1.402 * dcr
    g = y - 0.344136 * dcb - 0.714136 * dcr
    b = y + 1.772 * dcb
    return np.clip(np.stack([r, g, b], axis=-1), 0, 255).astype(np.uint8)

def apply_pair(rgb_u8, cb_table, cr_table):
    rgb = rgb_u8.astype(np.float64) / 255.0
    y, cb, cr = rgb_to_ycbcr(rgb)
    def ev(table, vals):
        x = np.frombuffer(table[0:16], np.uint8).astype(float)
        yy = np.frombuffer(table[16:32], np.uint8).astype(float)
        _, idx = np.unique(x, return_index=True)
        return np.interp(vals, x[idx], yy[idx])
    cb2 = ev(cb_table, cb); cr2 = ev(cr_table, cr)
    return ycbcr_to_rgb(y, cb2, cr2)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("base", type=Path)
    p.add_argument("--looks", type=Path, default=ROOT / "build" / "caduceus-fit" / "caduceus_looks.json")
    p.add_argument("--out", type=Path, default=ROOT / "build" / "caduceus-fit" / "preview.png")
    p.add_argument("--width", type=int, default=420, help="per-tile width")
    args = p.parse_args()
    entries = {e["key"]: e for e in json.loads(args.looks.read_text(encoding="utf-8"))}
    base = Image.open(args.base).convert("RGB")
    # downscale for speed
    w = args.width
    h = int(base.height * w / base.width)
    base = base.resize((w, h))
    base_u8 = np.asarray(base)
    order = ["portra400_hq", "velvia50_hq", "classicchrome_hq", "gold200_hq",
             "ektar100_hq", "cinestill800t_hq", "moriyama_bw_hq"]
    labels = {"portra400_hq": "人像柔暖 Portra", "velvia50_hq": "胶片色彩 Velvia",
              "classicchrome_hq": "经典铬 Cl.Chrome", "gold200_hq": "柯达金 Gold",
              "ektar100_hq": "风景鲜艳 Ektar", "cinestill800t_hq": "电影色调 CineStill",
              "moriyama_bw_hq": "森山黑白 B&W"}
    # grid: 4 columns x 4 rows (base + 7 looks, each shown old/new stacked)
    cols = 4
    rows = 4
    pad = 6; cap = 34
    tile_h = h + cap
    canvas = Image.new("RGB", (cols * (w + pad) + pad, rows * (tile_h * 2 + pad) + pad), (24, 24, 24))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
        small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
    except Exception:
        font = small = ImageFont.load_default()
    # base tile
    canvas.paste(base, (pad, pad + cap))
    draw.text((pad + 4, pad + 6), "原图 base", fill=(255, 255, 255), font=font)
    for i, key in enumerate(order):
        col = (i + 1) % cols
        row = (i + 1) // cols
        x0 = pad + col * (w + pad)
        y0 = pad + row * (tile_h * 2 + pad)
        look = next(l for l in HQ_LOOKS if l.key == key)
        old_cb = build_hq_table(look.cb_points); old_cr = build_hq_table(look.cr_points)
        e = entries[key]
        new_cb = bytes.fromhex(e["cb_table_hex"]); new_cr = bytes.fromhex(e["cr_table_hex"])
        old_img = Image.fromarray(apply_pair(base_u8, old_cb, old_cr))
        new_img = Image.fromarray(apply_pair(base_u8, new_cb, new_cr))
        canvas.paste(old_img, (x0, y0 + cap))
        canvas.paste(new_img, (x0, y0 + cap + h + 2))
        draw.text((x0 + 4, y0 + 4), labels[key], fill=(255, 220, 120), font=font)
        draw.text((x0 + 4, y0 + cap + h + 4), "↑safe-7  ↓新Caduceus", fill=(180, 180, 180), font=small)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.out)
    print("wrote", args.out, canvas.size)

if __name__ == "__main__":
    main()
