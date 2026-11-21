"""Exercise the portable SD menu-to-photo path against an existing photograph."""
import argparse
from functools import lru_cache
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ep5studio.project import atomic_write
from ep5studio.photo_input import load_preview
from ep5studio.photo_metadata import build_photo_exif
from ep5studio.wire import unpack_index

SOURCES = ("film_shot", "film_photo", "film", "film_fx", "film_fx_preset", "lut_bank", "lut_wheel",
           "lut_camera_menu", "lut_menu_adapter", "lut_wheel_draw", "lut_wheel_view",
           "lut", "look_store", "lut_job", "lut_preload", "lut_menu", "lut_menu_index")


@lru_cache(maxsize=64)
def linux_path(path):
    path = Path(path).resolve()
    if os.name != "nt":
        return str(path)
    return subprocess.run(["wsl", "-e", "wslpath", "-a", str(path)], capture_output=True,
                          check=True).stdout.decode("utf8").strip()


def build_driver(directory):
    directory.mkdir(parents=True, exist_ok=True)
    exe = linux_path(directory / "render_sd_frame")
    args = ["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-Ifirmware",
            "tools/render_sd_frame.c", *(f"firmware/{s}.c" for s in SOURCES), "-o", exe]
    subprocess.run((["wsl", "-e"] if os.name == "nt" else []) + args, cwd=ROOT, check=True)
    return exe


def frame_from_image(image):
    """Full-range 4:2:2, box average of the two source chroma samples."""
    ycc = np.asarray(image.convert("YCbCr"))
    h, w = ycc.shape[:2]
    if w % 2 or not (2 <= w <= 8192 and 1 <= h <= 8192):
        raise ValueError("Expected a photograph up to 8192×8192 with even width")
    out = np.empty((h, w // 2, 4), dtype=np.uint8)
    out[:, :, 0] = ycc[:, ::2, 0]
    out[:, :, 2] = ycc[:, 1::2, 0]
    for plane, channel in ((1, 1), (3, 2)):
        out[:, :, plane] = (ycc[:, ::2, channel].astype(np.uint16) + ycc[:, 1::2, channel] + 1) // 2
    return out.tobytes()


def image_from_frame(data, width, height):
    samples = np.frombuffer(data, np.uint8).reshape(height, width // 2, 4)
    ycc = np.empty((height, width, 3), dtype=np.uint8)
    ycc[:, ::2, 0], ycc[:, 1::2, 0] = samples[:, :, 0], samples[:, :, 2]
    for plane, channel in ((1, 1), (3, 2)):
        ycc[:, ::2, channel] = ycc[:, 1::2, channel] = samples[:, :, plane]
    return Image.frombytes("YCbCr", (width, height), ycc.tobytes()).convert("RGB")


def jpeg_options(row, bank, amount=None):
    return dict(quality=96, subsampling=1, exif=build_photo_exif(
        label=row["label"], bank=bank, amount_q8=row["amount_q8"] if amount is None else amount,
        number=row["number"], table_crc32=row["table_crc32"], picture_mode=row["picture_mode"],
        variant=row["variant"]))


def run_frame(exe, card, row, width, height, data, *, bank=1, amount=None, fx=None, seed=21745,
              stop=2**32 - 1, wheel=None):
    args = [exe, str(width), str(height), str(row["picture_mode"]), str(row["variant"]),
            str(row["amount_q8"] if amount is None else amount), *map(str, ("auto", 0, 0) if fx is None else fx),
            str(seed), str(stop), str(bank), linux_path(Path(card).resolve())]
    if wheel:
        args.append(linux_path(wheel))
    # Starting wsl.exe itself in a removable or temporary card directory can
    # leave a Windows directory handle behind after the Linux child exits.
    command = ["wsl", "-e", *args] if os.name == "nt" else args
    proc = subprocess.run(command, cwd=ROOT, input=data, capture_output=True)
    # WSL startup can print unrelated UTF-16 diagnostics before the C report.
    rows = [line for line in proc.stderr.split(b"\n") if line.lstrip(b"\x00\r ").startswith(b'{"result"')]
    if not rows:
        raise ValueError(proc.stderr.decode("utf8", "replace")[-1000:])
    report = json.loads(rows[-1].lstrip(b"\x00\r "))
    if not report["released"] or (proc.returncode == 0 and len(proc.stdout) != len(data)):
        raise ValueError("incomplete frame or unreleased look")
    if proc.returncode not in (0, 3) or (proc.returncode == 3 and (proc.stdout or report["result"] >= 0)):
        raise ValueError(f"inconsistent C driver result {proc.returncode}, {report}")
    return report, proc.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path)
    parser.add_argument("card", type=Path, help="extracted directory containing EP5LUT")
    parser.add_argument("label", help="short label from the bank index")
    parser.add_argument("out", type=Path)
    parser.add_argument("--bank", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--amount", type=int, choices=range(0, 257, 16))
    parser.add_argument("--fx", type=int, nargs=3, metavar=("GRAIN", "HALATION", "BLOOM"))
    parser.add_argument("--wheel", type=Path, help="saved EP5W edit for the chosen look")
    parser.add_argument("--assume-srgb", action="store_true", help="use only for known sRGB inputs without a profile")
    args = parser.parse_args()
    if args.out.resolve() == args.photo.resolve() or args.out.suffix.lower() not in (".jpg", ".jpeg"):
        parser.error("use a separate .jpg path for the preview")
    folder = args.card / "EP5LUT"
    if args.bank > 1:
        folder = folder / f"B{args.bank:02d}"
    matches = [r for r in unpack_index((folder / "INDEX.EP5").read_bytes()) if r["label"] == args.label]
    if len(matches) != 1:
        parser.error("the selected bank must contain exactly one matching label")
    prepared, input_space = load_preview(args.photo, args.assume_srgb, max_size=None)
    with prepared as image:
        w, h = image.size
        source = frame_from_image(image)
    with tempfile.TemporaryDirectory() as temp:
        exe = build_driver(Path(temp))
        report, result = run_frame(exe, args.card, matches[0], w, h, source, bank=args.bank,
                                   amount=args.amount, fx=args.fx, wheel=args.wheel)
    if report["result"] < 0 or (report["result"] == 0 and (args.amount if args.amount is not None else matches[0]["amount_q8"])):
        sys.exit(f"No styled JPEG was written: {report}")
    encoded = io.BytesIO()
    image_from_frame(result, w, h).save(encoded, format="JPEG", **jpeg_options(matches[0], args.bank, args.amount))
    atomic_write(args.out, encoded.getvalue())
    print(json.dumps({**report, "source": "decoded photo, host YUYV422", "input_space": input_space, "size": [w, h],
                      "frame_sha256": hashlib.sha256(result).hexdigest(), "file": str(args.out)}))


if __name__ == "__main__":
    main()
