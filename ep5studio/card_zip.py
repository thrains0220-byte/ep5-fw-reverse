"""Edit a verified three-bank SD data ZIP without the source bank archives."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import stat
import zlib
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from .cube import compile_rgb17, parse_cube
from .project import Binding, Project, SLOT_SPECS, SLOTS, short_label
from .recipe_fx import fx_sidecars, fx_sidecars_v2
from .wire import pack_index, pack_lut, unpack_index, unpack_lut


METADATA = {"CATALOG.JSON", "Caduceus-LICENSE.txt", "Caduceus-NOTICE.txt"}
CARD_PATH = re.compile(r"EP5LUT/(?:B0[23]/)?(?:INDEX\.EP5|FX\.EP5|L[0-9]{7}\.LUT)")
FX_ENCODERS = {b"EP5FXP01": fx_sidecars, b"EP5FXP02": fx_sidecars_v2}
MAX_BYTES = 4 * 1024 * 1024


def prefix(bank):
    return "EP5LUT/" if bank == 1 else f"EP5LUT/B{bank:02}/"


def encode_fx(encode, number, bank, index):
    # Plain colour cards can gain a first FX file. Keep their original looks
    # colour-only while retaining the upstream recipe attribution in the catalog.
    looks = [look if look.get("card_fx_enabled", True) else {**look, "spatial_omitted": {}}
             for look in bank["looks"]]
    return encode(number, {"looks": looks}, index)


def verify_card(content):
    """Read bounded, regular data files only; verify every row against its LUT, catalog and FX."""
    if len(content) > MAX_BYTES:
        raise ValueError("Card ZIP exceeds 4 MiB")
    try:
        with ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            names = {i.filename for i in infos}
            if (len(infos) != len(names) or not METADATA <= names or len(infos) > 57 or
                    sum(i.file_size for i in infos) > MAX_BYTES):
                raise ValueError("Invalid card ZIP directory")
            for info in infos:
                if (info.filename not in METADATA and not CARD_PATH.fullmatch(info.filename) or
                        info.flag_bits & 1 or info.compress_type not in (ZIP_STORED, ZIP_DEFLATED) or
                        stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)):
                    raise ValueError(f"Unexpected card entry: {info.filename}")
            files = {name: archive.read(name) for name in names}
        catalog = json.loads(files["CATALOG.JSON"].decode("utf8"))
        if (type(catalog["camera_verified"]) is not bool or catalog["encoding"] != "display-sRGB to display-sRGB" or
                not isinstance(catalog["banks"], list) or len(catalog["banks"]) != 3 or
                any(not files[name].strip() for name in METADATA)):
            raise ValueError("Expected a three-bank display-sRGB data catalog")
        expected = set(METADATA)
        for number, bank in enumerate(catalog["banks"], 1):
            base = prefix(number)
            index = files[base + "INDEX.EP5"]
            rows = unpack_index(index)
            expected.add(base + "INDEX.EP5")
            if len(rows) != len(bank["looks"]) or len(rows) > len(SLOTS):
                raise ValueError(f"Invalid bank {number} count")
            for look, row in zip(bank["looks"], rows):
                slot = SLOTS[look["slot"]]
                if not ((look["mode"], look["variant"], look["label"]) ==
                        (row["picture_mode"], row["variant"], row["label"]) ==
                        (slot["picture_mode"], slot["variant"], look["label"])):
                    raise ValueError(f"Bank {number} slot or name mismatch")
                lut = base + f"L{row['number']:07}.LUT"
                found, table = unpack_lut(files[lut])
                if (found != row["number"] or zlib.crc32(table) != row["table_crc32"] or
                        sha256(table).hexdigest() != look["table_sha256"]):
                    raise ValueError(f"Invalid table binding: {lut}")
                expected.add(lut)
            fx = base + "FX.EP5"
            if fx in files:
                encode = FX_ENCODERS.get(files[fx][:8])
                if encode is None or files[fx] != encode_fx(encode, number, bank, index):
                    raise ValueError(f"FX does not match bank {number}")
                expected.add(fx)
        if expected != names:
            raise ValueError("Card ZIP includes unreferenced members")
    except (BadZipFile, KeyError, TypeError, IndexError, AttributeError, UnicodeError) as err:
        raise ValueError("Invalid card ZIP or catalog") from err
    return files, catalog


def edit_card(source, output, edits):
    """(bank, replacement slot ID or None, label, raw cube, title, grain, source filename)."""
    source, output = Path(source), Path(output)
    if not edits or output.suffix.lower() != ".zip" or output.exists() or output.resolve() == source.resolve():
        raise ValueError("Choose at least one change and a new .zip output")
    if source.stat().st_size > MAX_BYTES:
        raise ValueError("Card ZIP exceeds 4 MiB")
    content = source.read_bytes()
    files, catalog = verify_card(content)
    changes = []
    edited = set()
    for bank_no, replace, label, raw, title, grain, filename in edits:
        if type(bank_no) is not int or not 1 <= bank_no <= 3:
            raise ValueError("Bank must be 1, 2 or 3")
        if len(raw) > 32 * 1024 * 1024 or grain not in ("off", "low", "medium", "high"):
            raise ValueError("Invalid cube size or grain")
        label = short_label(label)
        bank = catalog["banks"][bank_no - 1]
        looks = bank["looks"]
        slots = [look["slot"] for look in looks]
        if replace is None:
            slot = next((s[0] for s in SLOT_SPECS if s[0] not in slots), None)
            if slot is None:
                raise ValueError(f"Bank {bank_no} is full; choose an occupied slot to replace")
            position = len(slots)
        else:
            if replace not in slots:
                raise ValueError(f"Unoccupied replacement slot: {bank_no}/{replace}")
            slot, position = replace, slots.index(replace)
        if (bank_no, slot) in edited:
            raise ValueError(f"Multiple changes to {bank_no}/{slot}")
        if any(i != position and e["label"].casefold() == label.casefold() for i, e in enumerate(looks)):
            raise ValueError(f"Duplicate short name in bank {bank_no}: {label}")
        edited.add((bank_no, slot))
        index_name = prefix(bank_no) + "INDEX.EP5"
        rows = unpack_index(files[index_name])
        occupied = {r["number"] for i, r in enumerate(rows) if i != position}
        old_number = rows[position]["number"] if replace else None
        number = old_number if old_number is not None and old_number not in occupied else next(
            n for n in range(1, 17) if n not in occupied)
        cube = parse_cube(raw)
        table = compile_rgb17(cube)
        look_id = sha256(raw).hexdigest()
        spec = SLOTS[slot]
        entry = dict(key=f"personal-{slot}-{look_id[:12]}", name=cube.title or title, recipe=None, label=label,
                     slot=slot, mode=spec["picture_mode"], variant=spec["variant"], original_source=filename,
                     spatial_omitted={"grain": grain} if grain != "off" else {}, cube_id=look_id,
                     table_sha256=sha256(table).hexdigest())
        row = dict(number=number, table_crc32=zlib.crc32(table), amount_q8=256)
        change = {"bank": bank_no, "slot": slot, "source_filename": filename, "source_sha256": look_id,
                  "label": label}
        fx_name = prefix(bank_no) + "FX.EP5"
        previous_fx = files.get(fx_name)
        if not previous_fx and grain != "off":
            for previous in looks:
                previous["card_fx_enabled"] = False
        if replace:
            row["amount_q8"] = rows[position]["amount_q8"]
            change["replaced"] = looks[position]
            looks[position], rows[position] = entry, row
        else:
            looks.append(entry)
            rows.append(row)
        files[prefix(bank_no) + f"L{number:07}.LUT"] = pack_lut(number, table)
        # A content ID may legitimately be reused in slots of different strengths.
        # Here the stable on-card number identifies the existing binary exactly.
        numbers = {f"{r['number']:064x}": r["number"] for r in rows}
        sums = {f"{r['number']:064x}": r["table_crc32"] for r in rows}
        bindings = tuple(Binding(e["slot"], f"{r['number']:064x}", e["label"], r["amount_q8"])
                         for e, r in zip(looks, rows))
        files[index_name] = pack_index(Project("SD looks", bindings), numbers, sums)
        if previous_fx or grain != "off":
            encoder = FX_ENCODERS[previous_fx[:8]] if previous_fx else fx_sidecars_v2
            files[fx_name] = encode_fx(encoder, bank_no, bank, files[index_name])
        if "archive" in bank:
            bank["source_archive"] = {"name": bank.pop("archive"), "sha256": bank.pop("sha256")}
        changes.append(change)
    catalog.setdefault("card_edits", []).append({"parent_sha256": sha256(content).hexdigest(),
                                                "parent_camera_verified": catalog["camera_verified"],
                                                "changes": changes})
    catalog["camera_verified"] = False
    files["CATALOG.JSON"] = (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode("utf8")
    blob = BytesIO()
    with ZipFile(blob, "w") as archive:
        for name, data in sorted(files.items()):
            info = ZipInfo(name)
            info.create_system, info.external_attr = 3, 0o100644 << 16
            archive.writestr(info, data, compress_type=ZIP_DEFLATED)
    payload = blob.getvalue()
    if verify_card(payload)[0] != files:
        raise ValueError("Card ZIP readback mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    handle = output.open("xb")
    try:
        with handle:
            handle.write(payload)
        if output.read_bytes() != payload:
            raise OSError("Written card ZIP does not match verified output")
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output
