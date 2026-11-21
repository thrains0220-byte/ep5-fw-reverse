"""Export Caduceus display-sRGB looks to Studio .cube files and SD data archives."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ep5studio.export import export_project, validate_style_archive
from ep5studio.filmlooks import cube_text
from ep5studio.library import Library
from ep5studio.project import Binding, Project, SLOT_SPECS, atomic_write
from ep5studio.preview import preview_rgb8
from ep5studio.recipe_color import FILES, LABELS, RECIPES, RELEASE_FILES, REVISION, RecipeReference
from ep5studio.wire import unpack_lut, unpack_index


def _publish(path, content):
    if path.exists() and path.read_bytes() != content:
        raise ValueError(f"Different archive already exists: {path}")
    if not path.exists():
        atomic_write(path, content)


def export_archive(path, cubes):
    slots = {"Gold": "light-tone-i", "Portra400": "pale-light-i", "Velvia": "pop-art-i"}
    url = f"https://github.com/cakelesscoder/caduceus-ep7/tree/{REVISION}"
    with TemporaryDirectory() as tmp:
        library = Library(Path(tmp) / "library")
        bindings = []
        for name, file in cubes.items():
            look = library.import_file(file, input_encoding="srgb", output_encoding="srgb",
                                       source_url=url, notes="Caduceus v2 palette, tone and contrast. Display sRGB.")
            bindings.append(Binding(slots[name], look.id, "Portra" if name == "Portra400" else name, 256))
        stage = Path(tmp) / "reference.zip"
        export_project(Project("Caduceus Reference Tone", tuple(bindings)), library, stage)
        _publish(path, stage.read_bytes())
    validate_style_archive(path)


def export_banks(ref, out):
    """Bake all 29 released colour definitions, then verify from the archived bytes."""
    data_url = f"https://github.com/cakelesscoder/caduceus-ep7/blob/{REVISION}/bundles/library_v3.json"
    keys = list(ref.release)
    sample = np.random.default_rng(21745).integers(0, 256, (8192, 3), dtype=np.uint8)
    patches = np.array([[0, 0, 0], [64, 64, 64], [128, 128, 128], [192, 192, 192], [255, 255, 255],
                        [194, 142, 113], [75, 101, 163], [72, 133, 72], [231, 184, 64]], dtype=np.uint8)
    sample = np.concatenate([patches, sample])
    report = {"revision": REVISION, "source": data_url, "reference_sha256": FILES | RELEASE_FILES,
              "camera_verified": False, "encoding": "display-sRGB to display-sRGB", "strength_q8": 256,
              "patch_rgb8": patches.tolist(), "random_seed": 21745, "random_rgb8_count": 8192, "banks": []}
    with TemporaryDirectory() as temp:
        stage = Path(temp)
        library = Library(stage / "library")
        for start in range(0, len(keys), len(SLOT_SPECS)):
            number = start // len(SLOT_SPECS) + 1
            filename = f"EP5-Caduceus29-Bank{number:02d}.zip"
            bank = {"archive": filename, "looks": []}
            bindings = []
            for slot, key in zip(SLOT_SPECS, keys[start:]):
                definition = ref.release[key]
                data = cube_text(ref.cube(key), "Display sRGB; WB, contrast, H/S/M, blacks/whites, HSL.",
                                 attribution=f"Caduceus {REVISION}, library_v3/{key}, {definition['recipe']}.")
                omitted = {f: definition[f] for f in ("grain", "effect") if definition.get(f) not in ("off", None)}
                look = library.import_bytes(data, filename=key + ".cube", input_encoding="srgb", output_encoding="srgb",
                                            source_url=data_url, notes=f"{key}; spatial settings: {json.dumps(omitted)}")
                bindings.append(Binding(slot[0], look.id, LABELS[key], 256))
                bank["looks"].append({"key": key, "name": definition["name"], "recipe": definition["recipe"],
                                      "label": LABELS[key], "slot": slot[0], "mode": slot[2], "variant": slot[3],
                                      "original_source": definition.get("source"), "tone": definition["tone"],
                                      "spatial_omitted": omitted, "cube_id": look.id, "table_sha256": look.table_sha256})
            path = stage / filename
            export_project(Project(f"Caduceus 29 Color {number}/3", tuple(bindings)), library, path)
            validate_style_archive(path)
            with ZipFile(path) as archive:
                rows = unpack_index(archive.read("EP5LUT/INDEX.EP5"))
                if len(rows) != len(bindings):
                    raise ValueError("Bank index count mismatch")
                for entry, row in zip(bank["looks"], rows):
                    if ((entry["mode"], entry["variant"], entry["label"], 256) !=
                            (row["picture_mode"], row["variant"], row["label"], row["amount_q8"])):
                        raise ValueError(f"Bank index mismatch for {entry['key']}")
                    _, table = unpack_lut(archive.read(f"EP5LUT/L{row['number']:07d}.LUT"))
                    actual = preview_rgb8(sample[None, :, :], table)[0]
                    reference = ref.render8(entry["key"], sample) * 255
                    error = np.abs(actual - reference)
                    entry.update(patch_rgb8=actual[:len(patches)].tolist(),
                                 patch_reference_rgb8=np.rint(reference[:len(patches)]).astype(int).tolist(),
                                 mean_abs_rgb8=round(float(error.mean()), 3),
                                 p95_abs_rgb8=round(float(np.percentile(error, 95)), 3),
                                 max_abs_rgb8=round(float(error.max()), 3))
            bank["sha256"] = sha256(path.read_bytes()).hexdigest()
            report["banks"].append(bank)
        for bank in report["banks"]:
            _publish(out / bank["archive"], (stage / bank["archive"]).read_bytes())
        for name in ("LICENSE", "NOTICE"):
            atomic_write(out / ("Caduceus-" + name + ".txt"), ref.files[name])
        index = out / "catalog.json"
        atomic_write(index, (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode())
        return index


def export_single_card(out, *, fx_sidecars=None):
    """Collect the exact bytes from the three verified bank archives on one FAT volume."""
    out = Path(out)
    catalog = (out / "catalog.json").read_bytes()
    report = json.loads(catalog)
    if report.get("revision") != REVISION or len(report["banks"]) != 3:
        raise ValueError("Expected the three pinned release banks")
    files = {"CATALOG.JSON": catalog}
    fx_magic = None
    for name in ("LICENSE", "NOTICE"):
        files["Caduceus-" + name + ".txt"] = (out / ("Caduceus-" + name + ".txt")).read_bytes()
    for i, bank in enumerate(report["banks"], 1):
        leaf = f"EP5-Caduceus29-Bank{i:02d}.zip"
        if bank["archive"] != leaf:
            raise ValueError("Unexpected bank name")
        path = out / leaf
        if sha256(path.read_bytes()).hexdigest() != bank["sha256"]:
            raise ValueError(f"Changed source bank: {leaf}")
        validate_style_archive(path)
        dest = "EP5LUT/" if i == 1 else f"EP5LUT/B{i:02d}/"
        with ZipFile(path) as archive:
            for name in archive.namelist():
                if name.startswith("EP5LUT/"):
                    files[dest + name.removeprefix("EP5LUT/")] = archive.read(name)
            if fx_sidecars is not None:
                data = fx_sidecars(i, bank, archive.read("EP5LUT/INDEX.EP5"))
                if data[:8] not in (b"EP5FXP01", b"EP5FXP02") or (fx_magic and fx_magic != data[:8]):
                    raise ValueError("Mixed or invalid FX versions")
                fx_magic = data[:8]
                files[dest + "FX.EP5"] = data
    suffix = {None: "", b"EP5FXP01": "-FX", b"EP5FXP02": "-FX2"}[fx_magic]
    filename = out / f"EP5-Caduceus29-OneCard{suffix}.zip"
    with TemporaryDirectory() as temp:
        target = Path(temp) / filename.name
        with ZipFile(target, "x") as archive:
            for name, data in files.items():
                info = ZipInfo(name)
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compress_type=ZIP_DEFLATED)
        _publish(filename, target.read_bytes())
    with ZipFile(filename) as check:
        if check.namelist() != list(files) or any(check.read(name) != data for name, data in files.items()):
            raise ValueError("Combined card readback failed")
    return filename


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", type=Path, default=ROOT / "build/research/caduceus-color-78dbbc4")
    p.add_argument("--fetch-reference", action="store_true", help="download missing pinned reference files")
    p.add_argument("--out", type=Path, default=ROOT / "build/recipe-color")
    p.add_argument("--look", choices=tuple(RECIPES), action="append", help="default: export all three")
    p.add_argument("--archive", type=Path, help="also export a Studio SD data ZIP")
    p.add_argument("--release-library", action="store_true", help="generate all 29 v3 colour looks as three Studio banks")
    p.add_argument("--combine-banks", action="store_true", help="combine existing verified release banks from --out")
    effects = p.add_mutually_exclusive_group()
    effects.add_argument("--with-fx", action="store_true", help="include legacy FX.EP5 texture presets")
    effects.add_argument("--with-fx-v2", action="store_true", help="include FX.EP5 v2 presets with clarity")
    args = p.parse_args()
    try:
        fx = None
        if args.with_fx or args.with_fx_v2:
            if not (args.combine_banks or args.release_library):
                p.error("FX export requires --combine-banks or --release-library")
            from ep5studio.recipe_fx import fx_sidecars, fx_sidecars_v2
            fx = fx_sidecars_v2 if args.with_fx_v2 else fx_sidecars
        if (args.release_library or args.combine_banks) and (args.archive or args.look):
            p.error("--release-library generates its own three ZIP files; use --out to choose their directory")
        if args.combine_banks and not args.release_library:
            print(export_single_card(args.out, fx_sidecars=fx))
            return
        source = RecipeReference(args.reference, fetch=args.fetch_reference, release=args.release_library)
        if args.release_library:
            print(export_banks(source, args.out))
            print(export_single_card(args.out, fx_sidecars=fx))
            return
        if args.archive and args.archive.suffix.lower() != ".zip":
            p.error("--archive requires a .zip path")
        cubes = {}
        for name in dict.fromkeys(args.look or RECIPES):
            cube = source.cube(name)
            target = args.out / (name + "-Tone.cube")
            atomic_write(target, cube_text(cube, "sRGB display in/out. WB, contrast, H/S/M tone and HSL. Spatial effects excluded.",
                                           attribution=f"Caduceus web preview {REVISION}, library_v2/{RECIPES[name]}."))
            cubes[name] = target
            print(target)
        if args.archive:
            export_archive(args.archive, cubes)
            print(args.archive)
    except (OSError, ValueError, RuntimeError) as error:
        p.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
