"""Launch the offline E-P5 LUT Studio or exercise real startup and rendering."""
import argparse
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ep5studio.app import Studio, tk
from ep5studio.library import Library


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library",type=Path,help="local look library (default: user profile)")
    parser.add_argument("--preview-image",type=Path,help="open a local JPEG or PNG")
    parser.add_argument("--smoke-test",action="store_true",help="render a seeded look, then exit")
    args=parser.parse_args(argv)
    # A smoke run with no explicit library leaves the normal user's looks untouched.
    directory=tempfile.TemporaryDirectory(prefix="ep5-smoke-") if args.smoke_test and not args.library else None
    root=None
    try:
        lib=Library(args.library or (directory.name if directory else None))
        root=tk.Tk()
        if args.smoke_test:root.withdraw()
        studio=Studio(root,lib,args.preview_image if not args.smoke_test else None)
        if not args.smoke_test:
            root.mainloop()
            return 0
        limit=time.monotonic()+45
        while time.monotonic()<limit:
            root.update()
            if studio.start_ready and studio.display_ready and studio.result is not None:
                if sys.stdout is not None:
                    print(f"LUT Studio smoke OK: {len(studio.looks)} looks; {studio.result.size}; camera access: none")
                return 0
            if studio._errors:
                raise RuntimeError("; ".join(studio._errors))
            time.sleep(.015)
        raise RuntimeError("LUT Studio startup or render timed out")
    finally:
        if root is not None and args.smoke_test:
            if "studio" in locals():
                studio.close(force=True)
                studio._worker.join(timeout=2)
            else:
                root.destroy()
        if directory:directory.cleanup()


if __name__=="__main__":
    raise SystemExit(main())
