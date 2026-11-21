"""Export the tone, color wheel and white balance of three Caduceus sRGB previews."""
import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ep5studio.export import export_project, validate_style_archive
from ep5studio.filmlooks import cube_text
from ep5studio.library import Library
from ep5studio.project import Binding, Project, atomic_write
from ep5studio.recipe_color import RECIPES, REVISION, RecipeReference


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
        content = stage.read_bytes()
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f"Different archive already exists: {path}")
        if not path.exists():
            atomic_write(path, content)
    validate_style_archive(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", type=Path, default=ROOT / "build/research/caduceus-color-78dbbc4")
    p.add_argument("--fetch-reference", action="store_true", help="download missing pinned reference files")
    p.add_argument("--out", type=Path, default=ROOT / "build/recipe-color")
    p.add_argument("--look", choices=tuple(RECIPES), action="append", help="default: export all three")
    p.add_argument("--archive", type=Path, help="also export a Studio SD data ZIP")
    args = p.parse_args()
    try:
        source = RecipeReference(args.reference, fetch=args.fetch_reference)
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
