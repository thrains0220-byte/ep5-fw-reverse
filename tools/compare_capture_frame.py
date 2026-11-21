"""Compare an exported 8-bit packed 4:2:2 frame with a same-frame JPEG, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image


# Indexes into each four-byte pair, in the order Y0, Y1, Cb, Cr.
ORDERS = {"YUYV": (0, 2, 1, 3), "UYVY": (1, 3, 0, 2),
          "YVYU": (0, 2, 3, 1), "VYUY": (1, 3, 2, 0)}
MATRICES = {"BT.601": (0.299, 0.114), "BT.709": (0.2126, 0.0722)}
THRESHOLDS = {"min_pairs": 512, "min_luma_spread": 45.0, "min_chroma_std": 9.0,
              "max_mae": 4.0, "max_p95_pair_mae": 12.0, "max_quadrant_mae": 6.0,
              "min_runner_gap": 1.0, "min_relative_gap": 0.25, "min_agreeing_quadrants": 3}


def digest(path):
    with path.open("rb") as src:
        h = hashlib.sha256()
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rank_hypotheses(pairs, rgb, region):
    rankings = []
    for order, (i, j, u, v) in ORDERS.items():
        for limits in ("full", "limited"):
            y = pairs[:, [i, j]]
            cb, cr = pairs[:, u:u+1] - 128.0, pairs[:, v:v+1] - 128.0
            if limits == "limited":
                y = (y - 16.0) * (255.0 / 219.0)
                cb, cr = cb * (255.0 / 224.0), cr * (255.0 / 224.0)
            for matrix, (kr, kb) in MATRICES.items():
                r = y + 2 * (1 - kr) * cr
                b = y + 2 * (1 - kb) * cb
                g = (y - kr * r - kb * b) / (1 - kr - kb)
                predicted = np.stack((r, g, b), axis=-1).clip(0, 255)
                errors = np.abs(predicted - rgb).mean(axis=(1, 2))
                quadrant_mae = [float(errors[region == n].mean()) if np.any(region == n) else None
                                for n in range(4)]
                rankings.append(dict(order=order, range=limits, matrix=matrix, mae=float(errors.mean()),
                                     p95_pair_mae=float(np.percentile(errors, 95)), quadrant_mae=quadrant_mae))
    return sorted(rankings, key=lambda row: row["mae"])


def compare_capture(frame, jpeg, width, height, stride=None):
    frame, jpeg = Path(frame), Path(jpeg)
    if not (2 <= width <= 8192 and width % 2 == 0 and 1 <= height <= 8192):
        raise ValueError("Supply native dimensions up to 8192x8192, with even width")
    row_bytes = width * 2
    stride = row_bytes if stride is None else stride
    if stride < row_bytes or stride * height > 256 * 1024**2:
        raise ValueError("Invalid row stride or frame size")
    stored = frame.stat().st_size
    if stored not in (stride * height, (height - 1) * stride + row_bytes):
        raise ValueError("Frame length does not match the dimensions and stride")
    with Image.open(jpeg) as image:
        if image.format != "JPEG" or image.size != (width, height) or image.mode not in ("RGB", "L"):
            raise ValueError("Expected a matching stored JPEG raster in RGB or grayscale")
        # Use the stored raster, without EXIF rotation, resizing or a second JPEG encode.
        pixels = np.asarray(image.convert("RGB"))
    total = (width // 2) * height
    count = min(65536, total)
    rng = np.random.default_rng(21745)
    # One pair from each equally-sized interval across the raster. The fixed
    # seed is reproducible without locking to the phase of JPEG blocks.
    bounds = np.arange(count + 1, dtype=np.int64) * total // count
    pos = rng.integers(bounds[:-1], bounds[1:])
    y, xpair = np.divmod(pos, width // 2)
    x = 2 * xpair
    mapped = np.memmap(frame, dtype=np.uint8, mode="r")
    pairs = mapped[y[:, None] * stride + x[:, None] * 2 + np.arange(4)].astype(np.float32)
    del mapped
    rgb = pixels[y[:, None], x[:, None] + np.arange(2)].astype(np.float32)
    region = 2 * (y >= (height + 1) // 2) + (x >= (width + 1) // 2)
    rankings = rank_hypotheses(pairs, rgb, region)
    best, runner = rankings[:2]
    mean_rgb = rgb.mean(axis=1)
    luma = mean_rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    signal = {"luma_spread": float(np.percentile(luma, 95) - np.percentile(luma, 5)),
              "cb_std": float(((mean_rgb[:, 2] - luma) / 1.772).std()),
              "cr_std": float(((mean_rgb[:, 0] - luma) / 1.402).std())}
    gap = runner["mae"] - best["mae"]
    regions = best["quadrant_mae"]
    # Weak or grey quadrants do not count as independent votes for a choice.
    wins = sum(v is not None and min(r["quadrant_mae"][i] for r in rankings[1:]) - v >= 0.25
               for i, v in enumerate(regions))
    t = THRESHOLDS
    reasons = []
    if count < t["min_pairs"] or signal["luma_spread"] < t["min_luma_spread"] or min(
            signal["cb_std"], signal["cr_std"]) < t["min_chroma_std"]:
        reasons.append("insufficient_luma_or_colour_signal")
    if (best["mae"] > t["max_mae"] or best["p95_pair_mae"] > t["max_p95_pair_mae"] or
            max(v for v in regions if v is not None) > t["max_quadrant_mae"]):
        reasons.append("poor_same_frame_fit")
    if gap < max(t["min_runner_gap"], best["mae"] * t["min_relative_gap"]):
        reasons.append("ambiguous_runner_up")
    if wins < t["min_agreeing_quadrants"]:
        reasons.append("insufficient_regional_agreement")
    return dict(status="uncertain" if reasons else "candidate",
                candidate=None if reasons else {k: best[k] for k in ("order", "range", "matrix")},
                reasons=reasons, signal=signal, agreeing_quadrants=wins, runner_gap=gap, sampled_pairs=count,
                width=width, height=height, stride=stride, frame_sha256=digest(frame), jpeg_sha256=digest(jpeg),
                thresholds=t.copy(), rankings=rankings)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("frame", type=Path)
    p.add_argument("jpeg", type=Path)
    for name in ("width", "height"):
        p.add_argument("--" + name, type=int, required=True)
    p.add_argument("--stride", type=int, help="bytes per stored row, default width times two")
    args = p.parse_args()
    try:
        report = compare_capture(**vars(args))
    except (OSError, ValueError, Image.DecompressionBombError) as err:
        p.exit(2, f"{err}\n")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["candidate"] else 1


if __name__ == "__main__":
    sys.exit(main())
