"""Render a before/after color preview of each native film look (Windows numpy/Pillow)."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from tools.native_film_curves import LOOKS, build_table, axis_knots, eval_curve

def apply_chroma(rgb, look):
    cb_t = build_table(axis_knots(look.scale, look.cb_shift))
    cr_t = build_table(axis_knots(look.scale, look.cr_shift))
    r, g, b = (rgb * 255.0)[..., 0], (rgb * 255.0)[..., 1], (rgb * 255.0)[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    cb2 = eval_curve(cb_t, np.clip(np.round(cb), 0, 255).astype(int))
    cr2 = eval_curve(cr_t, np.clip(np.round(cr), 0, 255).astype(int))
    dcb, dcr = cb2 - 128, cr2 - 128
    r2 = np.clip(y + 1.402 * dcr, 0, 255)
    g2 = np.clip(y - 0.344136 * dcb - 0.714136 * dcr, 0, 255)
    b2 = np.clip(y + 1.772 * dcb, 0, 255)
    return np.stack([r2, g2, b2], axis=-1) / 255.0

# Synthetic test scene: color bars + skin + gray + sky + foliage gradients.
W, H = 256, 160
xx, yy = np.meshgrid(np.linspace(0, 1, W), np.linspace(0, 1, H))
scene = np.zeros((H, W, 3))
# hue sweep across the top
hue = xx
import colorsys
for i in range(W):
    r, g, b = colorsys.hsv_to_rgb(hue[0, i], 0.85, 0.95)
    scene[:40, i] = (r, g, b)
# skin tone band
scene[40:70, :] = (0.85, 0.62, 0.5)
# gray ramp
scene[70:95, :] = np.stack([xx[70:95, :]] * 3, axis=-1)
# sky blue
scene[95:120, :] = (0.3, 0.5, 0.85)
# foliage green
scene[120:145, :] = (0.2, 0.55, 0.25)
# red/orange
scene[145:, :] = (0.85, 0.3, 0.15)

cell_w, cell_h = W, H + 22
cols = 3
rows = (len(LOOKS) + 1 + cols - 1) // cols
canvas = Image.new("RGB", (cols * cell_w, rows * cell_h), (24, 24, 24))
draw = ImageDraw.Draw(canvas)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
except Exception:
    font = ImageFont.load_default()

def put(img, label, idx):
    r, c = divmod(idx, cols)
    canvas.paste(Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)), (c * cell_w, r * cell_h + 20))
    draw.text((c * cell_w + 4, r * cell_h + 2), label, fill=(255, 255, 255), font=font)

put(scene, "原图 / 中性输入", 0)
for i, look in enumerate(LOOKS):
    put(apply_chroma(scene.copy(), look), look.name_zh, i + 1)
out = ROOT / "build" / "film-looks-preview.png"
canvas.save(out)
print("saved", out)
