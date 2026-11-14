"""Diagnose camera JPEGs: ART mode + chroma/luma statistics.

Quantifies why a look may read as 'not film': mean chroma (saturation),
chroma spread, luma contrast, and Cb/Cr asymmetry (warm/cool cast).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
from PIL import Image
from PIL.ExifTags import IFD

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from olympus_tags import parse_camera_settings
import struct

def olympus_note(d: bytes):
    """Extract the Olympus MakerNote with correct TIFF-relative offsets."""
    i = 2
    tiff = None
    while i + 4 < len(d):
        if d[i] != 0xFF:
            break
        marker = d[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seglen = struct.unpack_from(">H", d, i + 2)[0]
        if marker == 0xE1 and d[i + 4:i + 10] == b"Exif\x00\x00":
            tiff = i + 10
            break
        i += 2 + seglen
    if tiff is None:
        return None
    bo = "<" if d[tiff:tiff + 2] == b"II" else ">"
    ifd0 = tiff + struct.unpack_from(bo + "I", d, tiff + 4)[0]

    def scan(ifd):
        n = struct.unpack_from(bo + "H", d, ifd)[0]
        exif_sub = None
        for k in range(n):
            p = ifd + 2 + k * 12
            tag = struct.unpack_from(bo + "H", d, p)[0]
            if tag == 0x927C:
                cnt = struct.unpack_from(bo + "I", d, p + 4)[0]
                off = tiff + struct.unpack_from(bo + "I", d, p + 8)[0]
                return d[off:off + cnt]
            if tag == 0x8769:
                exif_sub = tiff + struct.unpack_from(bo + "I", d, p + 8)[0]
        if exif_sub is not None:
            return scan(exif_sub)
        return None

    return scan(ifd0)

ART = {0: "Off", 1: "PopArt", 2: "RoughMono", 3: "ToyPhoto", 4: "Diorama",
       5: "PinHoleI", 6: "CrossProcess", 7: "SoftFocus", 8: "LightTone",
       9: "KeyLine", 10: "Watercolor", 11: "Vintage", 12: "PartColor",
       17: "PinHoleII", 18: "PinHoleIII"}

def stats(path):
    im = Image.open(path)
    art = pm = None
    note = olympus_note(path.read_bytes())
    if note:
        try:
            cs = parse_camera_settings(note)
            if cs.get("art_filter"): art = cs["art_filter"]["raw"][0]
            if cs.get("picture_mode"): pm = cs["picture_mode"]["raw"][0]
        except Exception:
            pass
    im = im.convert("RGB")
    im.thumbnail((1024, 1024))
    a = np.asarray(im).astype(np.float64) / 255.0
    r, g, b = a[..., 0] * 255, a[..., 1] * 255, a[..., 2] * 255
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    chroma = np.hypot(cb - 128, cr - 128)
    # exclude near-gray pixels for cast direction
    mask = chroma > 12
    return {
        "file": path.name,
        "art_raw": art, "art": ART.get(art, f"?{art}"), "picture_mode": pm,
        "mean_chroma": round(float(chroma.mean()), 2),
        "chroma_p90": round(float(np.percentile(chroma, 90)), 2),
        "mean_cb_dev": round(float((cb - 128)[mask].mean()), 2) if mask.any() else 0,
        "mean_cr_dev": round(float((cr - 128)[mask].mean()), 2) if mask.any() else 0,
        "luma_std": round(float(y.std()), 2),
        "luma_p5_p95": [round(float(np.percentile(y, 5)), 1), round(float(np.percentile(y, 95)), 1)],
        "sat_frac": round(float((chroma > 30).mean()), 3),
    }

def main():
    paths = [Path(p) for p in sys.argv[1:]]
    rows = [stats(p) for p in paths]
    print(f"{'file':16s} {'art':12s} {'chroma':>7s} {'p90':>6s} {'cbDev':>6s} {'crDev':>6s} {'lumaStd':>7s} {'satFrac':>7s}")
    for r in rows:
        print(f"{r['file']:16s} {r['art']:12s} {r['mean_chroma']:7.2f} {r['chroma_p90']:6.1f} "
              f"{r['mean_cb_dev']:6.2f} {r['mean_cr_dev']:6.2f} {r['luma_std']:7.2f} {r['sat_frac']:7.3f}")
    out = ROOT / "build" / "caduceus-fit" / "diagnosis.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)

if __name__ == "__main__":
    main()
