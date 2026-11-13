"""Launch EP5 LUT Studio v2 (7-slot firmware builder + film shelf UI)."""
import argparse
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ep5studio.app_v2 import StudioV2, tk
from ep5studio.library import Library


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, help="local look library")
    parser.add_argument("--smoke-test", action="store_true", help="render then exit")
    args = parser.parse_args(argv)
    directory = tempfile.TemporaryDirectory(prefix="ep5-smoke-") if args.smoke_test and not args.library else None
    root = None
    try:
        lib = Library(args.library or (directory.name if directory else None))
        root = tk.Tk()
        if args.smoke_test:
            root.withdraw()
        studio = StudioV2(root, lib)
        if not args.smoke_test:
            root.mainloop()
            return 0
        limit = time.monotonic() + 45
        while time.monotonic() < limit:
            root.update()
            if studio.looks:
                print(f"LUT Studio v2 smoke OK: {len(studio.looks)} looks; camera access: none")
                return 0
            time.sleep(.015)
        raise RuntimeError("LUT Studio v2 startup timed out")
    finally:
        if root is not None and args.smoke_test:
            if "studio" in locals():
                studio.close(force=True)
                studio._worker.join(timeout=2)
            else:
                root.destroy()
        if directory:
            directory.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
