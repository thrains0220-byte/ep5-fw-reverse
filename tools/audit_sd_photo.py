"""Render all banks against one source. Save only local photos and a non-photo receipt."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_sd_photo import build_driver, frame_from_image, image_from_frame, jpeg_options, run_frame
from ep5studio.photo_metadata import read_photo_metadata
from ep5studio.photo_input import load_preview
from ep5studio.card_zip import verify_card
from ep5studio.project import atomic_write
from ep5studio.wire import unpack_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--baseline", type=Path, help="compare against a receipt for the same input and named looks")
    parser.add_argument("--assume-srgb", action="store_true", help="accept an untagged, known sRGB photo")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    prepared, input_space = load_preview(args.photo, args.assume_srgb, max_size=None)
    with prepared as original:
        width, height = original.size
        source = frame_from_image(original)
    rows = []
    tile_w, tile_h = 256, 220
    _, catalog = verify_card(args.archive.read_bytes())
    expected = sum(len(b["looks"]) for b in catalog["banks"])
    sheet = Image.new("RGB", (tile_w * 5, tile_h * ((expected + 5) // 5)), "#202124")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=17)

    def tile(image, title, i):
        image = image.copy()
        image.thumbnail((tile_w - 8, tile_h - 32), Image.Resampling.LANCZOS)
        x, y = (i % 5) * tile_w, (i // 5) * tile_h
        sheet.paste(image, (x + (tile_w - image.width) // 2, y))
        draw.text((x + 6, y + tile_h - 26), title, font=font, fill="white")

    tile(image_from_frame(source, width, height), "Natural / source", 0)
    unique = set()
    with tempfile.TemporaryDirectory() as staging, ZipFile(args.archive) as archive:
        stage = Path(staging)
        exe = build_driver(stage)
        for bank, cat in enumerate(catalog["banks"], 1):
            prefix = "EP5LUT/" + (f"B{bank:02d}/" if bank > 1 else "")
            directory = stage / prefix
            directory.mkdir(parents=True, exist_ok=True)
            index = archive.read(prefix + "INDEX.EP5")
            (directory / "INDEX.EP5").write_bytes(index)
            (directory / "FX.EP5").write_bytes(archive.read(prefix + "FX.EP5"))
            for row, entry in zip(unpack_index(index), cat["looks"], strict=True):
                table = f"L{row['number']:07d}.LUT"
                (directory / table).write_bytes(archive.read(prefix + table))
                if row["label"] != entry["label"]:
                    raise ValueError("catalog/index mismatch")
                if not rows:
                    zero, passthrough = run_frame(exe, stage, row, width, height, source, amount=0)
                    if passthrough != source or zero["result"] != 0:
                        raise ValueError("full-size zero intensity changed pixels")
                report, output = run_frame(exe, stage, row, width, height, source, bank=bank)
                if report["result"] != 1 or report["preset"] != 1 or report["look_crc"] != row["table_crc32"]:
                    raise ValueError(f"{row['label']}: {report}")
                frame_hash = sha256(output).hexdigest()
                if frame_hash in unique or output == source:
                    raise ValueError(f"duplicate or unchanged output: {entry['key']}")
                unique.add(frame_hash)
                image = image_from_frame(output, width, height)
                ascii_names = {"森山黑白": "Moriyama-inspired B&W", "Acros": "Acros-inspired B&W", "TriX": "Tri-X-inspired B&W"}
                tile(image, ascii_names.get(row["label"], entry["name"]), len(rows) + 1)
                record = dict(key=entry["key"], bank=bank, label=row["label"], frame_sha256=frame_hash,
                              result=report["result"], preset=report["preset"], released=report["released"])
                if row["label"] == "森山黑白" or entry["key"] in ("gold", "portra", "velvia", "cinestill", "atrophy"):
                    filename = ("moriyama" if row["label"] == "森山黑白" else entry["key"]) + "-full.jpg"
                    image.save(args.out / filename, **jpeg_options(row, bank))
                    metadata = read_photo_metadata(args.out / filename)
                    if metadata["label"] != row["label"] or metadata["bank"] != bank:
                        raise ValueError("JPEG metadata mismatch")
                    with Image.open(args.out / filename) as jpeg:
                        jpeg.load()
                        if jpeg.size != (width, height):
                            raise ValueError("JPEG size mismatch")
                    record["jpeg"] = filename
                rows.append(record)
    if len(unique) != expected:
        raise ValueError("not all looks produced distinct renders")
    sheet.save(args.out / f"{expected}-looks.jpg", quality=94, subsampling=0)
    receipt = dict(camera_verified=False, backend="host full-range BT.601 YUYV422, Pillow JPEG",
                   size=[width, height], input_space=input_space, input_yuyv_sha256=sha256(source).hexdigest(),
                   archive_sha256=sha256(args.archive.read_bytes()).hexdigest(), zero_strength_exact=True,
                   looks=rows)
    if args.baseline:
        before = json.loads(args.baseline.read_bytes())
        if before["input_yuyv_sha256"] != receipt["input_yuyv_sha256"] or before["size"] != receipt["size"]:
            raise ValueError("Baseline must be a receipt for the same decoded input and dimensions")
        old = {(r["bank"], r["label"]): r["frame_sha256"] for r in before["looks"]}
        if len(old) != len(before["looks"]) or old.keys() != {(r["bank"], r["label"]) for r in rows}:
            raise ValueError("Baseline must contain the same uniquely named looks in each bank")
        receipt["comparison"] = {
            "baseline_archive_sha256": before["archive_sha256"],
            "changed": [{"bank": r["bank"], "label": r["label"]} for r in rows
                        if old[r["bank"], r["label"]] != r["frame_sha256"]]}
    atomic_write(args.out / "receipt.json", (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode())
    print(f"{len(rows)} unique full frames, {width} x {height}; {args.out}")


if __name__ == "__main__":
    main()
