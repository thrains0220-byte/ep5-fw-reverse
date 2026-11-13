"""Render the three-slot (Pin Hole I/II/III) before/after preview."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from tools.native_film_curves import build_table, axis_knots, eval_curve
from tools.build_native_film_pack import look_by_key
import colorsys

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

W, H = 256, 160
xx, yy = np.meshgrid(np.linspace(0, 1, W), np.linspace(0, 1, H))
scene = np.zeros((H, W, 3))
for i in range(W):
    scene[:40, i] = colorsys.hsv_to_rgb(xx[0, i], 0.85, 0.95)
scene[40:70, :] = (0.85, 0.62, 0.5)
scene[70:95, :] = np.stack([xx[70:95, :]] * 3, axis=-1)
scene[95:120, :] = (0.3, 0.5, 0.85)
scene[120:145, :] = (0.2, 0.55, 0.25)
scene[145:, :] = (0.85, 0.3, 0.15)

trio = [("gold200", "针孔I 柯达金200"), ("moriyama_bw", "针孔II 森山黑白"), ("velvia50", "针孔III 浓艳反转50")]
cw, ch = W, H + 22
canvas = Image.new("RGB", ((len(trio) + 1) * cw, ch), (24, 24, 24))
draw = ImageDraw.Draw(canvas)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
except Exception:
    font = ImageFont.load_default()

def put(img, label, idx):
    canvas.paste(Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)), (idx * cw, 20))
    draw.text((idx * cw + 4, 2), label, fill=(255, 255, 255), font=font)

put(scene, "原图 / 中性输入", 0)
for i, (key, label) in enumerate(trio):
    put(apply_chroma(scene.copy(), look_by_key(key)), label, i + 1)
out = ROOT / "build" / "film-trio-preview.png"
canvas.save(out)
print("saved", out)
