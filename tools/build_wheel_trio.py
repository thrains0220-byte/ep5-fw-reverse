"""Build and read back the pinned E-P5 Wheel Trio SD data in a local directory."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import ZipFile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.caduceus_to_ep5 import wheel_cube_bytes
from ep5studio.export import export_project
from ep5studio.library import Library
from ep5studio.project import Binding, Project, atomic_write
from ep5studio.wire import unpack_index, unpack_lut

REV = "78dbbc433ba0d04f1c31376937a98abede881526"
RECIPE_PATH = "sim/recipes/library_v2.json"
SOURCE_URL = f"https://github.com/cakelesscoder/caduceus-ep7/blob/{REV}/{RECIPE_PATH}"
RAW_URL = f"https://raw.githubusercontent.com/cakelesscoder/caduceus-ep7/{REV}/{RECIPE_PATH}"
RECIPE_SHA = "ecad3ffb50fc34e3ee65e079262e0b6f6e8a90fd0c27ae442a05818b385a6d4c"
ARCHIVE_SHA = "8fbfd70fa690a6b95643c134445061e06ec59f6833eccdf3799623c84ebd4b3d"
ARCHIVE_NAME = "EP5-Wheel-Trio.zip"
SPECS = [
    ("lib2_gold", "Gold", "light-tone-i", "Gold", 103),
    ("lib2_portra", "Portra400", "pale-light-i", "Portra", 102),
    ("lib2_velvia", "Velvia", "pop-art-i", "Velvia", 100),
]


def read_recipes(path):
    # Caduceus Apache-2.0 JSON. The same digest is required for online and offline inputs.
    with (path.open("rb") if path else urlopen(RAW_URL, timeout=20)) as fp:
        raw = fp.read(256 * 1024 + 1)
    if sha256(raw).hexdigest() != RECIPE_SHA:
        raise ValueError(f"incorrect library_v2.json SHA-256 (expected {RECIPE_SHA})")
    return json.loads(raw)["recipes"]


def rebuild(out, recipes):
    outputs = {}
    with TemporaryDirectory() as temp:
        lib = Library(Path(temp) / "library")
        bindings = []
        for key, stem, slot, label, _ in SPECS:
            filename = f"{stem}.cube"
            cube = wheel_cube_bytes(recipes[key], f"Caduceus library_v2.json / {key}")
            outputs[filename] = cube
            look = lib.import_bytes(cube, filename=filename, input_encoding="srgb", output_encoding="srgb",
                                    source_url=SOURCE_URL, notes=f"{key}: H/S/L wheel + WB chroma; Apache-2.0")
            bindings.append(Binding(slot, look.id, label, 256))
        project = Project("E-P5 Wheel Trio", tuple(bindings))
        outputs["wheel-trio.ep5project.json"] = (json.dumps(project.to_dict(), ensure_ascii=False, indent=2) + "\n").encode()
        stage = Path(temp) / ARCHIVE_NAME
        report = export_project(project, lib, stage)  # verifies ZIP, CRC, originals and recompiled tables
        outputs[ARCHIVE_NAME] = stage.read_bytes()
        digest = sha256(outputs[ARCHIVE_NAME]).hexdigest()
        if digest != ARCHIVE_SHA:
            raise ValueError(f"ZIP SHA-256 mismatch: {digest} (expected {ARCHIVE_SHA})")
        report.update(archive_sha256=digest, index_rows=[])
        with ZipFile(stage) as archive:
            index = archive.read("EP5LUT/INDEX.EP5")
            outputs["card-root/EP5LUT/INDEX.EP5"] = index
            for number, (row, spec) in enumerate(zip(unpack_index(index), SPECS, strict=True), 1):
                key, stem, _, label, mode = spec
                path = f"EP5LUT/L{number:07d}.LUT"
                data = archive.read(path)
                decoded, table = unpack_lut(data)
                actual = (row["picture_mode"], row["variant"], row["label"], row["amount_q8"],
                          row["number"], decoded, row["table_crc32"])
                if actual != (mode, 1, label, 256, number, number, zlib.crc32(table)):
                    raise ValueError(f"unexpected SD index data for {key}")
                if archive.read(f"SOURCE/L{number:07d}.cube") != outputs[f"{stem}.cube"]:
                    raise ValueError(f"unexpected source LUT for {key}")
                outputs["card-root/" + path] = data
                report["index_rows"].append(dict(row, bytes=len(table), table_sha256=sha256(table).hexdigest()))
    outputs["wheel-trio-readback.json"] = (json.dumps(report, indent=2) + "\n").encode()
    outputs["Neutral.cube"] = wheel_cube_bytes({"name": "Neutral"}, "Custom wheel recipe")
    # Compare existing files before publishing anything. A retry can complete a partial run.
    for name, data in outputs.items():
        path = out / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f"existing file differs, choose another --out directory: {path}")
    for name, data in outputs.items():
        path = out / name
        if not path.exists():
            atomic_write(path, data)
        if path.read_bytes() != data:
            raise OSError(f"output verification failed: {path}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "wheel-rgb17")
    parser.add_argument("--recipes", type=Path, help="use a local pinned library_v2.json instead of downloading")
    args = parser.parse_args()
    try:
        report = rebuild(args.out, read_recipes(args.recipes))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    print(f"{args.out / ARCHIVE_NAME}\nSHA-256 {report['archive_sha256']}")
    for row in report["index_rows"]:
        print(f"{row['number']}: {row['label']}  mode={row['picture_mode']}/{row['variant']}  "
              f"strength={row['amount_q8']}/256  bytes={row['bytes']}")


if __name__ == "__main__":
    main()
