"""Inspect one Olympus E-P5 via Windows WPD or pull explicitly selected originals."""
import argparse
import ctypes as ct
from collections import deque
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 64 * 1024 * 1024
CONTAINERS = {"{27E2E392-A111-48E0-AB0C-E17705A05F85}", "{99ED0160-17FF-4C44-9D98-1D7A6F941921}"}
IMAGE = "{EF2107D5-A52A-4243-A26B-62D4176D7603}"
UNSPECIFIED = "{28D8D31E-249C-454E-AABC-34883168E634}"
DEVICE_KEYS = "{26D4979A-E643-4626-9E2B-736DC0C92FDC}"
OBJECT_KEYS = "{EF6B490D-5CD8-437A-AFFC-DA8B60EE4A3C}"
RESERVED = re.compile(r"(?:AUX|CON|NUL|PRN|COM[0-9]|LPT[0-9])", re.I)


def new_session(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name) or RESERVED.fullmatch(name):
        raise ValueError("session must be one safe directory name, e.g. ep5-baseline-01")
    parent = ROOT / "sessions"
    parent.mkdir(mode=0o700, exist_ok=True)
    flags = getattr(parent.lstat(), "st_file_attributes", 0)
    if flags & stat.FILE_ATTRIBUTE_REPARSE_POINT or parent.is_symlink() or parent.resolve() != parent:
        raise ValueError("sessions must be a real project directory, not a link or junction")
    target = parent / name
    target.mkdir(mode=0o700, exist_ok=False)
    return target


def only_device(ids):
    if len(ids) != 1:
        raise ValueError("expected exactly one Windows portable device; unplug other WPD devices")
    if not re.search(r"(?:^|[#\\])USB[#\\]VID_07B4&PID_012F(?:[&#\\]|$)", ids[0], re.I):
        raise ValueError("USB identity differs from VID_07B4/PID_012F")
    return ids[0]


def check_model(identity):
    if str(identity.get("model", "")).strip().upper() != "E-P5":
        raise ValueError("WPD did not report the E-P5 model")


class WindowsWPD:
    """Narrow COM binding, with camera access confined to the read operations below."""
    def __init__(self):
        if sys.platform != "win32":
            raise OSError("Windows WPD is required")
        # An optional project-local, version-pinned installation. A venv also works.
        dep = ROOT / "build/usb-python-deps"
        if dep.is_dir():
            sys.path.insert(0, str(dep))
        import comtypes.client as client
        import comtypes
        self.client, self.com = client, comtypes
        gen = ROOT / "build/usb-com-gen"
        gen.mkdir(parents=True, exist_ok=True)
        client.gen_dir = str(gen)
        self.api = client.GetModule("PortableDeviceApi.dll")
        self.types = client.GetModule("PortableDeviceTypes.dll")
        self.free = ct.WinDLL("ole32").CoTaskMemFree
        self.free.argtypes, self.free.restype = [ct.c_void_p], None

    def key(self, guid, pid):
        return self.api._tagpropertykey(self.com.GUID(guid), pid)

    def create(self, cls, interface):
        return self.client.CreateObject(cls, interface=interface)

    def strings(self, capacity, fetch):
        # COM allocates each LPWSTR; retain raw addresses to free the caller-owned strings.
        buf = (ct.c_wchar_p * capacity)()
        ptrs = ct.cast(buf, ct.POINTER(ct.c_void_p))
        try:
            count = fetch(buf)
            if not 0 <= count <= capacity or any(not ptrs[i] for i in range(count)):
                raise ValueError("invalid WPD string count")
            return [buf[i] for i in range(count)]
        finally:
            for i in range(capacity):
                if ptrs[i]:
                    self.free(ptrs[i])

    @contextmanager
    def connect(self):
        manager = self.create(self.api.PortableDeviceManager, self.api.IPortableDeviceManager)
        get = manager._IPortableDeviceManager__com_GetDevices
        n = ct.c_ulong()
        get(None, ct.byref(n))
        if n.value != 1:
            raise ValueError("expected exactly one Windows portable device")
        def fetch(buf):
            get(buf, ct.byref(n))
            return n.value
        pnp = only_device(self.strings(1, fetch))
        client = self.create(self.types.PortableDeviceValues, self.api.IPortableDeviceValues)
        client.SetUnsignedIntegerValue(self.key("{204D9F0C-2292-4080-9F42-40664E70F859}", 9), 0x80000000)
        device = self.create(self.api.PortableDevice, self.api.IPortableDevice)
        device.Open(pnp, client)  # WPD_CLIENT_DESIRED_ACCESS = GENERIC_READ
        try:
            self.content = device.Content()
            self.props = self.content.Properties()
            ident = self.values("DEVICE", DEVICE_KEYS, (
                (3, "wpd_firmware", "str"), (4, "battery_percent", "GetUnsignedIntegerValue"),
                (6, "protocol", "str"), (7, "manufacturer", "str"), (8, "model", "str")))
            check_model(ident)
            yield ident
        finally:
            self.props = self.content = None
            device.Close()

    def values(self, oid, guid, fields):
        keys = self.create(self.types.PortableDeviceKeyCollection, self.api.IPortableDeviceKeyCollection)
        for pid, _, _ in fields:
            keys.Add(self.key(guid, pid))
        vals = self.props.GetValues(oid, keys)
        row = {}
        for pid, name, method in fields:
            k = self.key(guid, pid)
            try:
                if method == "str":
                    def fetch(buf):
                        vals._IPortableDeviceValues__com_GetStringValue(ct.byref(k), buf)
                        return 1
                    row[name] = self.strings(1, fetch)[0]
                else:
                    v = getattr(vals, method)(k)
                    row[name] = str(v).upper() if method == "GetGuidValue" else int(v)
            except self.com.COMError:
                pass  # individual properties may be unsupported; pull requires name/type/size/parent
        return row

    def object(self, oid):
        return dict(id=oid, **self.values(oid, OBJECT_KEYS, (
            (3, "parent", "str"), (4, "name", "str"), (7, "type", "GetGuidValue"),
            (11, "size", "GetUnsignedLargeIntegerValue"), (12, "filename", "str"))))

    def children(self, parent, limit):
        enum = self.content.EnumObjects(0, parent, None)
        def fetch(buf):
            got = ct.c_ulong()
            enum._IEnumPortableDeviceObjectIDs__com_Next(limit, buf, ct.byref(got))
            return got.value
        return self.strings(limit, fetch)

    def stream(self, oid):
        res = self.content.Transfer()
        key = self.key("{E81E79BE-34F0-41BF-B53F-F1A06AE87842}", 0)  # WPD_RESOURCE_DEFAULT
        stream, optimal = ct.POINTER(self.api.IStream)(), ct.c_ulong()
        res._IPortableDeviceResources__com_GetStream(oid, ct.byref(key), 0, ct.byref(optimal), ct.byref(stream))
        if not stream:
            raise OSError("WPD returned an empty read stream")
        def read(n):
            buf, got = stream.RemoteRead(n)  # STGM_READ = 0
            if not 0 <= got <= n:
                raise ValueError("invalid IStream read count")
            return ct.string_at(buf, got)
        return read, max(4096, min(optimal.value or 65536, 256 * 1024))


def inspect(wpd, limit):
    if not 1 <= limit <= 512:
        raise ValueError("inventory limit must be 1..512")
    rows, queue, seen = [], deque([("DEVICE", 0)]), {"DEVICE"}
    bounded = False
    while queue and len(rows) < limit:
        parent, depth = queue.popleft()
        remaining = limit - len(rows)
        ids = wpd.children(parent, remaining + 1)
        bounded |= len(ids) > remaining
        for oid in ids[:remaining]:
            if oid in seen:
                raise ValueError("duplicate/cyclic WPD object ID")
            seen.add(oid)
            row = wpd.object(oid)
            rows.append(row)
            if row.get("type") in CONTAINERS:
                if depth < 4:
                    queue.append((oid, depth + 1))
                else:
                    bounded = True
    return dict(objects=rows, inventory_limited=bounded or bool(queue))


def photo(row):
    name, size = row.get("filename", ""), row.get("size")
    if (not re.fullmatch(r"[a-zA-Z0-9_-]{1,8}\.(?:JPG|ORF)", name, re.I | re.ASCII)
            or RESERVED.fullmatch(name.split(".")[0]) or row.get("type") not in {IMAGE, UNSPECIFIED}
            or not row.get("parent")):
        raise ValueError("object is not a safe camera JPG/ORF original")
    if type(size) is not int or not 0 < size <= MAX_FILE:
        raise ValueError("missing/invalid WPD size or exceeds 64 MiB")
    return name, size


def pull(wpd, selections, target, files):
    # Object IDs may be recycled across Open calls. Require the filename
    # the operator actually selected and check *all* objects before fetching one.
    parsed = [s.partition(":") for s in selections]
    ids = [oid for oid, _, _ in parsed]
    if not 1 <= len(ids) <= 16 or len(set(ids)) != len(ids) or any(
            not re.fullmatch(r"o[0-9A-Fa-f]{1,16}", oid) or not expected
            for oid, _, expected in parsed):
        raise ValueError("specify 1..16 unique selections as ID:FILENAME from inspect")
    rows = [wpd.object(oid) for oid in ids]
    names = [photo(row)[0].upper() for row in rows]
    if names != [expected.upper() for _, _, expected in parsed]:
        raise ValueError("object ID now has a different filename; inspect again")
    if len(set(names)) != len(names):
        raise ValueError("different objects have the same local filename")
    for oid, before in zip(ids, rows):
        name, size = photo(before)
        dest = target / name
        part = target / (name + ".part")
        count, sha, head = 0, hashlib.sha256(), b""
        fp = part.open("xb")
        try:
            with fp:
                read, chunk = wpd.stream(oid)
                try:
                    while count < size:
                        want = min(chunk, size - count)
                        block = read(want)
                        if not 0 < len(block) <= want:
                            raise ValueError("short or oversized WPD stream")
                        head += block[:max(0, 8-len(head))]
                        sha.update(block)
                        fp.write(block)
                        count += len(block)
                    if read(1):
                        raise ValueError("WPD stream exceeds declared object size")
                finally:
                    del read
            if name.upper().endswith(".JPG"):
                valid = head.startswith(b"\xff\xd8\xff")
            else:
                valid = len(head) == 8 and head[:4] in (b"IIRO", b"IIRS", b"MMOR")
            if not valid:
                raise ValueError("WPD data signature disagrees with original filename")
            if wpd.object(oid) != before:
                raise ValueError("WPD object metadata changed during transfer")
            if os.name == "nt":  # Windows rename fails if destination exists (also on FAT).
                part.rename(dest)
            else:
                os.link(part, dest)
        finally:
            part.unlink(missing_ok=True)
        files.append(dict(id=oid, path=name, bytes=count, sha256=sha.hexdigest(), parent=before["parent"]))


def save(target, report):
    with (target / "manifest.json").open("x", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)
        fp.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("inspect", "pull"):
        p = sub.add_parser(action)
        p.add_argument("--session", required=True, help="new directory name inside local sessions/")
        if action == "inspect":
            p.add_argument("--limit", type=int, default=120)
        else:
            p.add_argument("--id", dest="ids", metavar="ID:FILENAME", action="append", required=True)
    args = parser.parse_args()
    try:
        target = new_session(args.session)
        report = dict(status="incomplete", action=args.action, camera_writes=False, files=[])
        try:
            wpd = WindowsWPD()
            with wpd.connect() as identity:
                report["device"] = identity
                if args.action == "inspect":
                    report.update(inspect(wpd, args.limit))
                else:
                    pull(wpd, args.ids, target, report["files"])
            report["status"] = "complete"
        finally:
            save(target, report)
    except Exception as exc:
        parser.exit(1, f"Collection stopped: {exc}\n")
    print(f"Saved {args.action} report to {target / 'manifest.json'}")


if __name__ == "__main__":
    main()
