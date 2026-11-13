"""Original film-inspired looks generated from documented color recipes.

Every table here is project-original procedural math, not extracted camera or
third-party vendor data, and not a measured reproduction of any branded film
stock. Names describe the visual genre only. All looks map sRGB display input
to sRGB display output with pure per-color transforms, so they compile to the
same bounded 17^3 wire format as imported .cube files.
"""
import numpy as np

from .cube import Cube

REC709 = np.array([0.2126, 0.7152, 0.0722])
REC601 = np.array([0.299, 0.587, 0.114])


def grid(side):
    """Red-fastest [B,G,R,3] float grid in [0,1], matching wire order."""
    b, g, r = np.indices((side, side, side), dtype=np.float64)
    return np.stack((r, g, b), axis=-1) / (side - 1)


def clamp(rgb):
    return np.clip(rgb, 0.0, 1.0)


def luma(rgb, weights=REC709):
    return rgb @ weights


def sat(rgb, factor):
    y = luma(rgb)[..., None]
    return y + (rgb - y) * factor


def s_curve(rgb, strength):
    """Symmetric soft S-curve; fixed points at 0, 0.5 and 1."""
    return rgb + strength * (rgb - 0.5) * (1.0 - np.abs(2.0 * rgb - 1.0)) * 2.0


def lift_gamma_gain(rgb, lift, gamma, gain):
    x = np.clip(rgb, 1e-6, 1.0) ** np.asarray(gamma)
    return np.asarray(lift) * (1.0 - x) + np.asarray(gain) * x


def wb(rgb, r_mul, b_mul):
    out = rgb.copy()
    out[..., 0] *= r_mul
    out[..., 2] *= b_mul
    return out


def tone_rgb(rgb, shadows, mids, highs):
    """Smooth per-channel tone map through five anchor points."""
    anchors = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    out = np.empty_like(rgb)
    for channel, curve in enumerate((shadows, mids, highs)):
        points = np.array(curve)
        out[..., channel] = np.interp(rgb[..., channel], anchors, points)
    return out


def bleach(rgb, amount):
    """Bleach-bypass: luminance overlay with partial desaturation."""
    y = luma(rgb)[..., None]
    overlay = np.where(y < 0.5, 2.0 * rgb * y, 1.0 - 2.0 * (1.0 - rgb) * (1.0 - y))
    mixed = rgb * (1.0 - amount) + overlay * amount
    return sat(mixed, 0.82)


def split_tone(rgb, shadow_rgb, high_rgb, strength):
    y = luma(rgb)[..., None]
    shadow_w = (1.0 - y) ** 2
    high_w = y ** 2
    tint = (np.asarray(shadow_rgb) - 0.5) * shadow_w + (np.asarray(high_rgb) - 0.5) * high_w
    return rgb + strength * tint


def faded(rgb, black_lift, white_drop):
    return black_lift + rgb * (white_drop - black_lift)


def channel_cross(rgb, matrix):
    return rgb @ np.asarray(matrix).T


def moriyama(rgb):
    """High-contrast monochrome genre: deep blacks, bright highs."""
    y = luma(rgb, REC601)
    y = clamp(s_curve(y, 0.85))
    y = np.clip((y - 0.06) / 0.88, 0.0, 1.0)
    y = clamp(s_curve(y, 0.55))
    return np.repeat(y[..., None], 3, axis=-1)


def gold_200(rgb):
    """Warm consumer-negative genre: golden highs, gentle teal shadows."""
    x = wb(rgb, 1.055, 0.925)
    x = sat(x, 1.13)
    x = tone_rgb(x,
                 shadows=(0.015, 0.245, 0.49, 0.75, 0.99),
                 mids=(0.0, 0.255, 0.515, 0.765, 1.0),
                 highs=(0.03, 0.235, 0.47, 0.72, 0.955))
    x = split_tone(x, (0.44, 0.52, 0.56), (0.58, 0.53, 0.42), 0.35)
    return clamp(s_curve(x, 0.18))


def gold_100(rgb):
    """Fine-grain daylight-negative genre: cleaner, milder than Gold 200."""
    x = wb(rgb, 1.03, 0.955)
    x = sat(x, 1.06)
    x = tone_rgb(x,
                 shadows=(0.005, 0.25, 0.5, 0.755, 0.995),
                 mids=(0.0, 0.25, 0.51, 0.76, 1.0),
                 highs=(0.015, 0.24, 0.485, 0.735, 0.975))
    return clamp(s_curve(x, 0.12))


def ultramax_400(rgb):
    """Punchy consumer-negative genre: warm, saturated, snappy contrast."""
    x = wb(rgb, 1.06, 0.94)
    x = sat(x, 1.22)
    x = s_curve(x, 0.3)
    x = tone_rgb(x,
                 shadows=(0.01, 0.24, 0.485, 0.75, 0.99),
                 mids=(0.0, 0.25, 0.51, 0.765, 1.0),
                 highs=(0.02, 0.235, 0.48, 0.74, 0.97))
    return clamp(x)


def colorplus_200(rgb):
    """Budget-negative genre: warm cast, slightly muted greens."""
    x = wb(rgb, 1.05, 0.93)
    x = sat(x, 1.08)
    x = channel_cross(x, ((1.0, 0.02, 0.0), (0.0, 0.97, 0.01), (0.0, 0.02, 0.98)))
    x = tone_rgb(x,
                 shadows=(0.02, 0.25, 0.49, 0.745, 0.985),
                 mids=(0.01, 0.25, 0.505, 0.755, 0.995),
                 highs=(0.03, 0.24, 0.48, 0.73, 0.96))
    return clamp(s_curve(x, 0.15))


def portra_160(rgb):
    """Soft portrait-negative genre: pastel palette, protected skin warmth."""
    x = wb(rgb, 1.02, 0.985)
    x = sat(x, 0.9)
    x = lift_gamma_gain(x, (0.035, 0.03, 0.028), (0.98, 1.0, 1.02), (0.985, 0.98, 0.975))
    x = split_tone(x, (0.48, 0.5, 0.53), (0.55, 0.52, 0.47), 0.3)
    return clamp(s_curve(x, 0.08))


def portra_400(rgb):
    """Warm portrait-negative genre: creamier highs than Portra 160."""
    x = wb(rgb, 1.045, 0.955)
    x = sat(x, 0.95)
    x = lift_gamma_gain(x, (0.045, 0.035, 0.03), (0.97, 0.99, 1.03), (0.99, 0.975, 0.955))
    x = split_tone(x, (0.47, 0.5, 0.54), (0.57, 0.53, 0.44), 0.35)
    return clamp(s_curve(x, 0.1))


def ektar_100(rgb):
    """Vivid landscape-negative genre: deep saturation, cool shadows."""
    x = sat(rgb, 1.3)
    x = s_curve(x, 0.32)
    x = split_tone(x, (0.44, 0.49, 0.58), (0.54, 0.51, 0.46), 0.3)
    x = wb(x, 1.02, 0.99)
    return clamp(x)


def velvia_50(rgb):
    """Slide-chrome genre: strong saturation and contrast, magenta-leaning."""
    x = wb(rgb, 1.03, 1.01)
    x = sat(x, 1.45)
    x = s_curve(x, 0.45)
    x = tone_rgb(x,
                 shadows=(0.0, 0.235, 0.48, 0.75, 1.0),
                 mids=(0.0, 0.245, 0.5, 0.755, 1.0),
                 highs=(0.0, 0.24, 0.49, 0.75, 1.0))
    return clamp(x)


def provia_100f(rgb):
    """Neutral slide-chrome genre: faithful color, modest snap."""
    x = sat(rgb, 1.12)
    x = s_curve(x, 0.22)
    return clamp(x)


def classic_chrome(rgb):
    """Documentary-chrome genre: subdued color, hard tonality, cool air."""
    x = sat(rgb, 0.82)
    x = wb(x, 0.99, 1.03)
    x = s_curve(x, 0.38)
    x = split_tone(x, (0.42, 0.5, 0.6), (0.52, 0.51, 0.48), 0.4)
    return clamp(x)


def acros(rgb):
    """Fine-grain monochrome genre: smooth midtones, clean contrast."""
    y = luma(rgb, np.array([0.25, 0.65, 0.10]))
    y = clamp(s_curve(y, 0.4))
    y = np.clip((y - 0.02) / 0.96, 0.0, 1.0)
    return np.repeat(y[..., None], 3, axis=-1)


def tri_x_400(rgb):
    """Classic reportage monochrome genre: gritty contrast curve."""
    y = luma(rgb, np.array([0.30, 0.59, 0.11]))
    y = clamp(s_curve(y, 0.7))
    y = np.clip((y - 0.05) / 0.9, 0.0, 1.0)
    y = clamp(s_curve(y, 0.35))
    return np.repeat(y[..., None], 3, axis=-1)


def superia_400(rgb):
    """Everyday consumer-negative genre: green-cyan bias, lively warmth."""
    x = wb(rgb, 1.02, 0.97)
    x = channel_cross(x, ((0.99, 0.03, 0.0), (0.0, 1.02, 0.02), (0.0, 0.04, 0.97)))
    x = sat(x, 1.15)
    x = tone_rgb(x,
                 shadows=(0.01, 0.25, 0.49, 0.745, 0.985),
                 mids=(0.0, 0.26, 0.515, 0.76, 0.995),
                 highs=(0.015, 0.245, 0.49, 0.74, 0.975))
    return clamp(s_curve(x, 0.2))


def cine_tone(rgb):
    """Flat cinema-log-style display genre: lifted blacks, rolled highlights."""
    x = sat(rgb, 0.88)
    x = lift_gamma_gain(x, (0.06, 0.06, 0.065), (1.02, 1.0, 0.98), (0.93, 0.93, 0.92))
    x = split_tone(x, (0.45, 0.5, 0.57), (0.54, 0.52, 0.47), 0.25)
    return clamp(x)


def bleach_bypass(rgb):
    """Silver-retention process genre: desaturated, metallic contrast."""
    x = bleach(rgb, 0.65)
    x = s_curve(x, 0.35)
    return clamp(x)


def cross_process(rgb):
    """Cross-processed slide genre: shifted greens/blues, hard contrast."""
    x = tone_rgb(rgb,
                 shadows=(0.0, 0.27, 0.53, 0.78, 1.0),
                 mids=(0.03, 0.28, 0.55, 0.78, 0.98),
                 highs=(0.0, 0.2, 0.44, 0.72, 1.0))
    x = sat(x, 1.25)
    x = s_curve(x, 0.4)
    return clamp(x)


LOOK_SPECS = (
    ("Identity", "恒等校验", lambda rgb: rgb,
     "单位变换，用于校验链路不改色。"),
    ("MoriyamaHighContrastBW", "森山风·高反差黑白", moriyama,
     "高反差粗颗粒黑白风格取向；颗粒/暗角不在 LUT 范围内。"),
    ("Gold200", "金调·暖负片200", gold_200,
     "暖金色消费负片取向：金黄高光、微青阴影。"),
    ("Gold100", "金调·日光负片100", gold_100,
     "更干净温和的暖调日光负片取向。"),
    ("UltraMax400", "艳彩·消费负片400", ultramax_400,
     "高饱和暖调消费负片取向，反差明快。"),
    ("ColorPlus200", "暖彩·平价负片200", colorplus_200,
     "偏暖略哑光的平价负片取向。"),
    ("Portra160", "柔肤·人像负片160", portra_160,
     "低饱和奶油色人像负片取向，肤色偏暖。"),
    ("Portra400", "柔肤·人像负片400", portra_400,
     "比160更暖更柔的人像负片取向。"),
    ("Ektar100", "浓彩·风景负片100", ektar_100,
     "高饱和风景负片取向，阴影偏冷。"),
    ("Velvia50", "极致·反转片50", velvia_50,
     "浓艳反转片取向：高饱和高反差。"),
    ("Provia100F", "标准·反转片100", provia_100f,
     "中性微艳反转片取向。"),
    ("ClassicChrome", "纪实·经典铬", classic_chrome,
     "低饱和硬调纪实取向，空气感偏冷。"),
    ("Acros100", "细粒·黑白100", acros,
     "细腻平滑的黑白取向。"),
    ("TriX400", "报道·黑白400", tri_x_400,
     "经典报道黑白取向，反差硬朗。"),
    ("Superia400", "日常·负片400", superia_400,
     "青绿倾向的日常负片取向。"),
    ("CineTone", "电影·灰调", cine_tone,
     "低反差电影灰调取向，黑位抬升。"),
    ("BleachBypass", "银留·漂白", bleach_bypass,
     "漂白跳过工艺取向：金属感低饱和。"),
    ("CrossProcess", "交叉·冲印", cross_process,
     "交叉冲印取向：色偏强烈、反差硬。"),
)


def look_names():
    return tuple(name for name, _title, _fn, _note in LOOK_SPECS)


def build_cube(name, side=17):
    for spec_name, title, fn, note in LOOK_SPECS:
        if spec_name != name:
            continue
        values = clamp(fn(grid(side)))
        return Cube(title, side, values), note
    raise KeyError(name)


def cube_text(cube, note):
    header = (f'TITLE "{cube.title}"\n'
              f'# Original project look inspired by a film genre; not a measured stock reproduction\n'
              f'# {note}\n'
              f'LUT_3D_SIZE {cube.side}\n')
    flat = cube.values.reshape(-1, 3)
    return (header + "\n".join(" ".join(f"{v:.10f}" for v in row) for row in flat) + "\n").encode("utf-8")
