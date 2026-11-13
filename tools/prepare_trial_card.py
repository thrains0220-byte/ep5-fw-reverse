"""Prepare an identified removable SD card for an E-P5 RC2 trial; never start an update."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_native_film import CANDIDATE_SHA256
from tools.build_trial_kit import CANDIDATE_ZIP, STOCK_ZIP, CARD_FILE, SIZE
from tools.inspect_ep5 import STOCK_SHA256
from tools.mtp_collect import new_session

MARKER = Path("DCIM/100OLYMP/PB130080.JPG")
BASELINE = Path("sessions/mtp-stock-baseline-20261113/manifest.json")
PART = "E1089999.RC2.part"
MAX_BACKUP = 128 * 1024 * 1024
MAX_ENTRIES = 1024


def drive_root(value):
    if not re.fullmatch(r"[A-Za-z]:[/\\]", value) or value[0].upper() in "CD":
        raise ValueError("specify the explicit removable card drive root (e.g. E:/); C: and D: are refused")
    if sys.platform != "win32":
        raise ValueError("card preparation requires Windows")
    return Path(value[0].upper() + ":\\")


def checked(path, directory=False):
    info = path.lstat()
    if (getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise ValueError(f"unexpected file type, link or junction: {path}")
    return info


def volume(root):
    """Read only: identify a mounted removable volume. Refuse changed/absent media."""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetDriveTypeW.argtypes, k.GetDriveTypeW.restype = [wintypes.LPCWSTR], wintypes.UINT
    if k.GetDriveTypeW(str(root)) != 2:
        raise ValueError(f"{root} is not a removable volume")
    checked(root, directory=True)
    get = k.GetVolumeNameForVolumeMountPointW
    get.argtypes, get.restype = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD], wintypes.BOOL
    name = ctypes.create_unicode_buffer(128)
    if not get(str(root), name, len(name)):
        raise ctypes.WinError(ctypes.get_last_error())
    return name.value


def digest(path, size):
    if checked(path).st_size != size:
        raise ValueError(f"unexpected file size: {path}")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for _ in range(0, size, 1024 * 1024):
            h.update(f.read(min(1024 * 1024, size - f.tell())))
        if f.tell() != size or f.read(1):
            raise ValueError(f"file changed while reading: {path}")
    return h.hexdigest()


def firmware_spec(kind):
    if kind == "rc2":
        return CANDIDATE_ZIP, CANDIDATE_SHA256[2], "reviewed RC2"
    if kind == "stock":
        return STOCK_ZIP, STOCK_SHA256, "official E-P5 1.8"
    raise ValueError("firmware kind must be rc2 or stock")


def candidate(kind="rc2"):
    name, expected, label = firmware_spec(kind)
    path = ROOT / "build/ep5-trial" / name
    if path.resolve(strict=True) != path or checked(path).st_size > 80 * 1024 * 1024:
        raise ValueError("unexpected local trial ZIP")
    with ZipFile(path) as z:
        entries = [i for i in z.infolist() if i.filename == CARD_FILE]
        if len(entries) != 1 or entries[0].file_size != SIZE:
            raise ValueError("missing, duplicate or wrong-size firmware member")
        data = z.read(entries[0])
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"image differs from the {label}")
    return data


def baseline():
    path = ROOT / BASELINE
    if path.resolve(strict=True) != path or checked(path).st_size > 1024 * 1024:
        raise ValueError("unexpected local baseline manifest")
    rows = [r for r in json.loads(path.read_text(encoding="utf-8"))["files"] if r["path"] == MARKER.name]
    if (len(rows) != 1 or type(rows[0]["bytes"]) is not int or not 0 < rows[0]["bytes"] <= 64 * 1024 * 1024
            or not re.fullmatch("[0-9a-f]{64}", rows[0]["sha256"])):
        raise ValueError("invalid baseline photo entry")
    return rows[0]["bytes"], rows[0]["sha256"]


def match_card(root, ident, marker):
    if volume(root) != ident:
        raise ValueError("removable volume changed")
    checked(root / "DCIM", directory=True)
    checked(root / MARKER.parent, directory=True)
    if digest(root / MARKER, marker[0]) != marker[1]:
        raise ValueError("baseline photo differs; this is not the selected card")


def optional(path, directory=False):
    try:
        return checked(path, directory)
    except FileNotFoundError:
        return None


def backup(source, dest):
    """Copy the full prior DCOLYMP tree, checking contents read back locally."""
    if optional(source, directory=True) is None:
        return None
    dest.mkdir()
    files = {}
    count = total = 0
    todo = [(source, dest)]
    while todo:
        folder, target = todo.pop()
        checked(folder, directory=True)
        for path in folder.iterdir():
            count += 1
            if count > MAX_ENTRIES:
                raise ValueError("DCOLYMP backup exceeds the entry limit")
            out = target / path.name
            if stat.S_ISDIR(path.lstat().st_mode):
                checked(path, directory=True)
                out.mkdir()
                todo.append((path, out))
                continue
            n = checked(path).st_size
            total += n
            if total > MAX_BACKUP:
                raise ValueError("DCOLYMP backup exceeds 128 MiB")
            with path.open("rb") as inp, out.open("xb") as fp:
                left = n
                while left:
                    block = inp.read(min(left, 1024 * 1024))
                    if not block:
                        raise ValueError("backup source shortened")
                    fp.write(block)
                    left -= len(block)
                if inp.read(1):
                    raise ValueError("backup source grew")
                fp.flush()
                os.fsync(fp.fileno())
            sha = digest(out, n)
            if sha != digest(path, n):
                raise ValueError(f"backup verification failed: {path}")
            files[path.relative_to(source).as_posix().casefold()] = {"bytes": n, "sha256": sha}
    return files


def report(session, state):
    tmp = session / "report.tmp"
    with tmp.open("x", encoding="utf-8") as fp:
        json.dump(state, fp, indent=2)
        fp.write("\n")
        fp.flush()
        os.fsync(fp.fileno())
    tmp.replace(session / "report.json")


def prepare(card, session, kind="rc2"):
    root = drive_root(card)
    if root == Path(ROOT.anchor):
        raise ValueError("project files and backups must be on a different volume")
    _, expected, label = firmware_spec(kind)
    data, marker = candidate(kind), baseline()
    ident = volume(root)
    match_card(root, ident, marker)
    local = new_session(session)
    folder = root / "DCOLYMP"
    dest = root / CARD_FILE
    part = folder / (PART if kind == "rc2" else "E1089999.STOCK.part")
    state = dict(status="incomplete", card=str(root), volume=ident, photo=MARKER.as_posix(),
                 photo_sha256=marker[1], firmware_kind=kind, expected_firmware_sha256=expected,
                 bin_published=False, flash_started=False)
    owned = created = None
    report(local, state)
    try:
        saved = backup(folder, local / "DCOLYMP")
        state.update(previous_folder=saved is not None, backup=saved)
        report(local, state)
        match_card(root, ident, marker)
        if saved is None:
            folder.mkdir()
            created = checked(folder, directory=True)
        else:
            checked(folder, directory=True)
        # An existing .part, whatever its contents, is not ours to remove.
        with part.open("xb") as fp:
            owned = os.fstat(fp.fileno())
            if fp.write(data) != len(data):
                raise OSError("short write to the card")
            fp.flush()
            os.fsync(fp.fileno())
        if digest(part, SIZE) != expected:
            raise ValueError(f"staged {label} failed read-back")
        match_card(root, ident, marker)
        checked(folder, directory=True)
        old = (saved or {}).get(dest.name.casefold())
        if old is None:
            if optional(dest) is not None:
                raise ValueError("update appeared after backup; refusing to replace")
            part.rename(dest)  # Windows does not overwrite with rename.
        else:
            if digest(dest, old["bytes"]) != old["sha256"]:
                raise ValueError("existing camera update changed after backup")
            part.replace(dest)
        owned = None
        state["bin_published"] = True
        match_card(root, ident, marker)
        checked(folder, directory=True)
        if digest(dest, SIZE) != expected:
            raise ValueError(f"published {label} failed read-back; do not install")
        state["status"] = "verified_card"
    except BaseException as exc:
        state["error"] = str(exc)
        if state["bin_published"]:
            state["status"] = "published_unverified_do_not_install"
        elif owned or created:
            # Never unlink on a swapped volume or remove a pre-existing .part.
            try:
                match_card(root, ident, marker)
                checked(folder, directory=True)
                if owned and os.path.samestat(owned, checked(part)):
                    part.unlink()
                if created and os.path.samestat(created, checked(folder, directory=True)):
                    folder.rmdir()
            except (OSError, ValueError) as cleanup:
                state["cleanup_error"] = str(cleanup)
        raise
    finally:
        report(local, state)
    return local / "report.json"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--card", required=True, help="explicit removable drive root, e.g. E:/")
    p.add_argument("--session", required=True, help="new backup/report name under local sessions/")
    p.add_argument("--kind", choices=("rc2", "stock"), default="rc2",
                   help="rc2: Soft Chrome (default); stock: exact official 1.8 recovery")
    args = p.parse_args()
    try:
        print(prepare(args.card, args.session, args.kind))
    except (KeyError, BadZipFile, OSError, ValueError) as exc:
        p.exit(1, f"Card preparation failed; do not install: {exc}\n")


if __name__ == "__main__":
    main()
