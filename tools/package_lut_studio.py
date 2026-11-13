"""Build a Windows one-folder desktop distribution in an isolated local venv."""
import argparse
from pathlib import Path
import subprocess
import sys
import venv


ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/"build"
DEPS=("pyinstaller==6.16.0","numpy==2.4.6","pillow==12.3.0")


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse",type=Path,help="install only from an existing wheel directory")
    parser.add_argument("--no-install",action="store_true",help="reuse the prepared local packaging venv")
    args=parser.parse_args(argv)
    if sys.platform!="win32" or sys.version_info[:2]!=(3,11) or sys.maxsize<=2**32:
        parser.error("use Windows x64 Python 3.11 with Tcl/Tk")
    base=BUILD/"lut-studio-packenv"
    py=base/"Scripts/python.exe"
    if not py.exists():
        if args.no_install:parser.error("--no-install requires the prepared build/lut-studio-packenv")
        venv.EnvBuilder(with_pip=True).create(base)
    def call(commands):
        subprocess.run([str(py),*map(str,commands)],cwd=ROOT,check=True)
    if not args.no_install:
        install=["-m","pip","install","--disable-pip-version-check","--only-binary=:all:"]
        if args.wheelhouse:
            install.extend(["--no-index","--find-links",args.wheelhouse.resolve()])
        call([*install,*DEPS])
    dist=BUILD/"lut-studio-dist"
    # Only the entry module and its import closure: no --add-data for the
    # workspace, firmware, sessions, sample photographs or the user's look library.
    call(["-m","PyInstaller","--noconfirm","--onedir","--windowed","--name","EP5LUTStudio",
          "--paths",ROOT,"--distpath",dist,"--workpath",BUILD/"lut-studio-pyinstaller",
          "--specpath",BUILD/"lut-studio-spec","--exclude-module","scipy",
          ROOT/"tools/run_lut_studio.py"])
    exe=dist/"EP5LUTStudio/EP5LUTStudio.exe"
    if not exe.is_file():raise RuntimeError("missing built executable")
    subprocess.run([str(exe),"--smoke-test"],cwd=dist,timeout=90,check=True)
    print(exe)


if __name__=="__main__":
    main()
