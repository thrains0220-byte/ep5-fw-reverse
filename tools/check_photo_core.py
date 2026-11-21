"""Cross-build the stand-alone image, menu and preview components under Linux/WSL."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = ROOT / "toolchains/mn103/bin"
MODULES = ("film_shot", "film_photo", "film", "film_fx", "film_fx_preset", "film_preview",
           "lut_bank", "lut_wheel", "lut_camera_menu", "lut_wheel_view", "lut_wheel_draw",
           "lut_menu_adapter", "lut", "look_store", "lut_job", "lut_preload", "lut_menu", "lut_menu_index")


def main():
    dst = ROOT / "build/photo-render/photo-core.o"
    dst.parent.mkdir(parents=True, exist_ok=True)
    cc = PREFIX / "mn10300-elf-gcc"
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        objects = []
        for name in MODULES:
            obj = work / (name + ".o")
            subprocess.run([cc, "-mno-am33", "-std=c99", "-Os", "-ffreestanding", "-fno-builtin",
                            "-fno-tree-loop-distribute-patterns", "-Wall", "-Wextra", "-Werror",
                            "-I", ROOT / "firmware", "-c", ROOT / "firmware" / (name + ".c"),
                            "-o", obj], check=True)
            objects.append(obj)
        product = work / "photo-core.o"
        subprocess.run([cc, "-mno-am33", "-r", "-nostdlib", *objects, "-lgcc", "-o", product], check=True)
        missing = subprocess.check_output([PREFIX / "mn10300-elf-nm", "-u", product], text=True).strip()
        if missing:
            raise RuntimeError(f"Unresolved symbols: {missing}")
        subprocess.run([PREFIX / "mn10300-elf-size", product], check=True)
        dst.write_bytes(product.read_bytes())
    print(dst)


if __name__ == "__main__":
    main()
