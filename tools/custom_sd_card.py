"""Add display-sRGB .cube looks to a packaged card, or replace a specific bank and slot."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ep5studio.export import export_project, validate_style_archive
from ep5studio.card_zip import MAX_BYTES, edit_card, verify_card
from ep5studio.filmlooks import build_cube, cube_text
from ep5studio.library import Library
from ep5studio.project import Binding, Project, SLOT_SPECS, atomic_write, short_label
from ep5studio.recipe_fx import fx_sidecars
from tools.export_recipe_color import export_single_card


def personal_card(reference, output, additions):
    """(short label, cube bytes, title, grain). Other banks stay byte-identical."""
    reference, output = Path(reference), Path(output)
    if reference.is_file():
        return edit_card(reference, output, [(3, None, *entry, entry[0] + ".cube") for entry in additions])
    if output.exists() or output.suffix.lower() != ".zip":
        raise ValueError("Choose a new .zip output file")
    if not additions:
        raise ValueError("Add at least one personal look")
    catalog = json.loads((reference / "catalog.json").read_bytes())
    bank = catalog["banks"][2]
    entries = bank["looks"]
    labels = [short_label(label) for label, *_ in additions]
    old_labels = {entry["label"].casefold() for entry in entries}
    if (len(entries) + len(labels) > len(SLOT_SPECS) or
            len(old_labels | {s.casefold() for s in labels}) != len(entries) + len(labels)):
        raise ValueError("Bank 3 has insufficient space or duplicate short names")
    with TemporaryDirectory() as temp:
        stage = Path(temp)
        library = Library(stage / "library")
        for name in ("Caduceus-LICENSE.txt", "Caduceus-NOTICE.txt", "EP5-Caduceus29-Bank01.zip",
                     "EP5-Caduceus29-Bank02.zip"):
            shutil.copyfile(reference / name, stage / name)
        filename = "EP5-Caduceus29-Bank03.zip"
        source = reference / filename
        if bank["archive"] != filename or sha256(source.read_bytes()).hexdigest() != bank["sha256"]:
            raise ValueError("Reference bank 3 does not match its catalog")
        validate_style_archive(source)
        with ZipFile(source) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            original = Project.from_dict(manifest["project"])
            bindings = list(original.bindings)
            for info in manifest["looks"]:
                library.import_bytes(archive.read(info["source"]), filename=f"L{info['number']:07d}.cube",
                                     input_encoding="srgb", output_encoding="srgb", source_url=info["source_url"],
                                     notes=info["notes"])
        used = {b.slot_id for b in bindings}
        slots = [s for s in SLOT_SPECS if s[0] not in used]
        for slot, label, (_, raw, title, grain) in zip(slots, labels, additions):
            look = library.import_bytes(raw, filename="personal.cube", input_encoding="srgb",
                                        output_encoding="srgb", notes=title)
            bindings.append(Binding(slot[0], look.id, label, 256))
            entries.append(dict(key="personal-" + label, name=title, recipe=None, label=label,
                                slot=slot[0], mode=slot[2], variant=slot[3], original_source=None,
                                spatial_omitted={"grain": grain} if grain != "off" else {},
                                cube_id=look.id, table_sha256=look.table_sha256))
        export_project(Project("E-P5 Personal", tuple(bindings)), library, stage / filename)
        bank["sha256"] = sha256((stage / filename).read_bytes()).hexdigest()
        catalog["personal"] = {"bank": 3, "added_labels": labels}
        atomic_write(stage / "catalog.json", json.dumps(catalog, ensure_ascii=False, indent=2).encode("utf8"))
        result = export_single_card(stage, fx_sidecars=fx_sidecars)
        atomic_write(output, result.read_bytes())
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", nargs="?", type=Path)
    p.add_argument("--list-slots", action="store_true", help="show the bank, ART slot and current look")
    source = p.add_mutually_exclusive_group()
    source.add_argument("--card", type=Path, help="existing one-card ZIP (default: bundled 29-look card)")
    source.add_argument("--reference", type=Path, help="legacy source bank directory, for a bank-3 addition")
    p.add_argument("--bank", type=int, choices=(1, 2, 3), default=3, help="destination bank for additions")
    p.add_argument("--street-bw", action="store_true", help="include the project's Moriyama-inspired, Tri-X and Acros looks")
    p.add_argument("--add-srgb-cube", action="append", default=[], metavar="LABEL=FILE",
                   help="add a normalized display-sRGB to display-sRGB 3D LUT")
    p.add_argument("--replace-srgb-cube", action="append", nargs=3, default=[],
                   metavar=("BANK", "SLOT", "LABEL=FILE"),
                   help="replace an existing ART slot (1-14 in ART order, or its slot ID)")
    args = p.parse_args()
    edits = []
    source_zip = args.card or ROOT / "looks/EP5-Caduceus29-OneCard-FX2.zip"

    def read_cube(spec):
        label, sep, name = spec.partition("=")
        path = Path(name)
        if not sep or path.suffix.lower() != ".cube" or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Expected LABEL=FILE.cube up to 32 MiB")
        return label, path.read_bytes(), label, "off", path.name

    try:
        if args.list_slots:
            if args.out or args.reference or args.street_bw or args.add_srgb_cube or args.replace_srgb_cube:
                raise ValueError("--list-slots accepts only an optional --card")
            if source_zip.stat().st_size > MAX_BYTES:
                raise ValueError("Card ZIP exceeds 4 MiB")
            _, catalog = verify_card(source_zip.read_bytes())
            for n, bank in enumerate(catalog["banks"], 1):
                looks = {e["slot"]: e for e in bank["looks"]}
                for i, (slot, _, _, _) in enumerate(SLOT_SPECS, 1):
                    look = looks.get(slot)
                    text = f"{look['label']}  {look['name']}" if look else "[empty]"
                    print(f"{n}  {i:2}  {slot:16}  {text}")
            return
        if args.out is None:
            raise ValueError("Provide a new output ZIP path, or use --list-slots")
        if args.street_bw:
            for key, label, grain in (("MoriyamaHighContrastBW", "森山黑白", "high"), ("TriX400", "TriX", "medium"),
                                      ("Acros100", "Acros", "low")):
                cube, note = build_cube(key)
                edits.append((args.bank, None, label, cube_text(cube, note), cube.title, grain, f"{key}.cube"))
        for spec in args.add_srgb_cube:
            edits.append((args.bank, None, *read_cube(spec)))
        for bank, slot, spec in args.replace_srgb_cube:
            if slot.isascii() and slot.isdecimal() and 1 <= int(slot) <= len(SLOT_SPECS):
                slot = SLOT_SPECS[int(slot) - 1][0]
            edits.append((int(bank), slot, *read_cube(spec)))
        if args.reference:
            if args.replace_srgb_cube or args.bank != 3:
                raise ValueError("Use --card for replacements or a different bank")
            print(personal_card(args.reference, args.out, [e[2:6] for e in edits]))
        else:
            print(edit_card(source_zip, args.out, edits))
    except (ValueError, OSError) as err:
        p.exit(1, f"{err}\n")


if __name__ == "__main__":
    main()
