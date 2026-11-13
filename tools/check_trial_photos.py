"""Inspect copies of E-P5 RAW+JPEG captures; never infer firmware success."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys

if __package__:
    from .olympus_tags import parse_camera_settings
else:
    from olympus_tags import parse_camera_settings


FRAME = (4608, 3456)
SETTINGS = {33434: "exposure_seconds", 33437: "f_number", 34855: "iso",
            37386: "focal_length_mm", 41987: "white_balance_mode"}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for block in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def camera_tags(tags, exif):
    make, model = (str(tags.get(k, "")).strip(" \x00") for k in (271, 272))
    if not make.upper().startswith("OLYMPUS") or model.upper() != "E-P5":
        raise ValueError(f"expected Olympus E-P5 camera tags; got {make!r}, {model!r}")
    when = str(exif.get(36867, "")).strip(" \x00")
    if not when:
        raise ValueError("missing DateTimeOriginal")
    return dict(make=make, model=model, date_time_original=when)


def orf_tags(fp):
    from PIL.TiffImagePlugin import ImageFileDirectory_v2
    h = fp.read(8)
    if len(h) != 8 or h[:4] not in (b"IIRO", b"IIRS", b"MMOR"):
        raise ValueError("invalid Olympus ORF header")
    # ORF uses classic TIFF IFD offsets with an Olympus magic number. Adapt
    # only the in-memory header for the metadata reader; LibRaw sees original bytes.
    magic = b"*\0" if h[:2] == b"II" else b"\0*"
    tags = ImageFileDirectory_v2(h[:2] + magic + h[4:])
    fp.seek(tags.next)
    tags.load(fp)
    if 34665 not in tags:
        raise ValueError("ORF missing ExifIFD")
    fp.seek(tags[34665])
    exif = ImageFileDirectory_v2(prefix=h[:2])
    exif.load(fp)
    return camera_tags(tags, exif)


def read_orf(path):
    import rawpy
    with path.open("rb") as fp:
        rec = orf_tags(fp)
    with rawpy.imread(str(path)) as raw:
        pixels = raw.raw_image_visible  # unpacks sensor samples, not embedded preview
        if pixels.ndim != 2 or pixels.shape[1] < FRAME[0] or pixels.shape[0] < FRAME[1]:
            raise ValueError(f"unexpected E-P5 raw mosaic shape: {pixels.shape}")
        rec.update(visible_width=pixels.shape[1], visible_height=pixels.shape[0],
                   sample_range=[int(pixels.min()), int(pixels.max())])
    return dict(file=path.name, sha256=digest(path), **rec)


def read_jpeg(path, regions):
    from PIL import Image
    from simplejpeg import decode_jpeg
    data = path.read_bytes()
    with Image.open(io.BytesIO(data), formats=["JPEG"]) as im:
        if im.size != FRAME or im.mode != "RGB":
            raise ValueError(f"expected full-size RGB JPEG {FRAME}, got {im.size}, {im.mode}")
        tags = im.getexif()
        exif = tags.get_ifd(34665)
        rec = camera_tags(tags, exif)
        rec["camera_settings"] = parse_camera_settings(exif.get(37500))
        rec["settings"] = {label: str(exif[tag]) if tag in exif else None
                           for tag, label in SETTINGS.items()}
        # Ordinary tolerant JPEG decoders can fill missing scanlines with
        # grey while reporting full dimensions. Reject even recoverable errors.
        pixels = decode_jpeg(data, colorspace="RGB", strict=True)
        if pixels.shape != (im.height, im.width, 3):
            raise ValueError("inconsistent decoded JPEG dimensions")
        scores = []
        for x, y, w, h in regions:
            if min(x, y) < 0 or min(w, h) < 1 or x + w > im.width or y + h > im.height:
                raise ValueError(f"region outside stored JPEG: {x} {y} {w} {h}")
            region = pixels[y:y+h, x:x+w]
            spread = region.max(axis=2) - region.min(axis=2)
            scores.append(dict(xywh=[x, y, w, h], mean_rgb=region.mean(axis=(0, 1)).round(3).tolist(),
                               mean_rgb_spread=round(float(spread.mean()), 3)))
        rec.update(width=im.width, height=im.height, regions=scores,
                   decoded_rgb_sha256=hashlib.sha256(pixels).hexdigest())
    return dict(file=path.name, sha256=hashlib.sha256(data).hexdigest(), **rec)


def check_pair(jpg, regions):
    if jpg.suffix.lower() not in (".jpg", ".jpeg"):
        raise ValueError(f"expected a JPEG capture path: {jpg}")
    matches = [p for p in jpg.parent.iterdir() if p.name.casefold() == (jpg.stem + ".orf").casefold()]
    if len(matches) != 1:
        raise ValueError(f"{jpg}: expected one same-stem ORF in the same directory")
    jpeg = read_jpeg(jpg, regions)
    orf = read_orf(matches[0])
    if jpeg["date_time_original"] != orf["date_time_original"]:
        raise ValueError(f"{jpg.name} and {orf['file']} have different capture times")
    return dict(jpeg=jpeg, orf=orf)


def inspect(before, after=None, regions=()):
    regions = regions or [(0, 0, *FRAME)]
    base = check_pair(before, regions)
    report = dict(status="original_pair_decoded", before=base,
                  firmware_installation="unverified", film_effect="requires_controlled_scene_review")
    if after is not None:
        test = check_pair(after, regions)
        if any(base[k]["sha256"] == test[k]["sha256"] for k in ("jpeg", "orf")):
            raise ValueError("duplicate input: before/after need independent shutter captures")
        a, b = base["jpeg"], test["jpeg"]
        report.update(status="two_original_pairs_decoded", after=test, comparison=dict(
            same_decoded_rgb=a["decoded_rgb_sha256"] == b["decoded_rgb_sha256"],
            different_settings=[k for k in a["settings"] if a["settings"][k] != b["settings"][k]],
            missing_settings=[k for k in a["settings"] if None in (a["settings"][k], b["settings"][k])],
            mean_rgb_spread_delta=[round(j["mean_rgb_spread"] - i["mean_rgb_spread"], 3)
                                   for i, j in zip(a["regions"], b["regions"])]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path, help="stock Pin Hole I original JPG")
    parser.add_argument("--after", type=Path, help="candidate Pin Hole I original JPG")
    parser.add_argument("--region", nargs=4, type=int, metavar=("X", "Y", "WIDTH", "HEIGHT"),
                        action="append", help="stored JPEG coordinates; repeat for colour/grey patches")
    parser.add_argument("--out", type=Path, help="new report file; default: stdout")
    args = parser.parse_args()
    try:
        report = inspect(args.before, args.after, args.region)
        result = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out is None:
            print(result)
        else:
            with args.out.open("x", encoding="utf-8") as fp:
                fp.write(result + "\n")
    except ImportError as exc:
        parser.exit(2, f"Missing decoder ({exc}); install Pillow rawpy simplejpeg.\n")
    except Exception as exc:
        parser.exit(1, f"Photo check failed: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
