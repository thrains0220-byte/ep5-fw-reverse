"""Export optional texture settings bound to the SD bank's validated LUT rows."""
import struct
import zlib

from .wire import unpack_index


HEADER = struct.Struct("<8sHHII")
ROW = struct.Struct("<HBBHHIBBBB")
GRAIN = {"off": 0, "low": 25, "medium": 50, "high": 75}
HALO_TINT = {"warm": 0, "amber": 1, "red": 2}
CLARITY_GAIN = (12, 22, 32, 42, 52)


def strengths(spatial):
    """Translate explicitly specified Caduceus effects into local approximations."""
    grain = GRAIN[spatial.get("grain", "off")]
    effect = spatial.get("effect")
    if not effect or effect.get("type") not in ("bloom", "halation"):
        return grain, 0, 0, 0
    amount = effect.get("strength")
    if type(amount) is not int or not 1 <= amount <= 5:
        raise ValueError("Invalid texture effect strength")
    tint = effect.get("tint", "red" if effect["type"] == "halation" else None)
    if tint in HALO_TINT:
        return grain, ((amount + 1) // 2) * 25, 0, HALO_TINT[tint]
    if tint in (None, "neutral"):
        return grain, 0, amount * 20, 0
    raise ValueError("Unknown texture effect tint")


def fx_sidecars(bank_number, bank, index):
    """Create a legacy v1 FX.EP5 file."""
    return _fx_sidecar(bank_number, bank, index, version=1)


def fx_sidecars_v2(bank_number, bank, index):
    """Create a v2 FX.EP5 file with the original recipe's local clarity."""
    return _fx_sidecar(bank_number, bank, index, version=2)


def _fx_sidecar(bank_number, bank, index, *, version):
    if bank_number not in (1, 2, 3):
        raise ValueError("Invalid texture bank number")
    rows = unpack_index(index)
    looks = bank["looks"]
    if len(looks) != len(rows) or len(rows) > 14:
        raise ValueError("Texture catalog and bank counts differ")
    records = []
    for look, row in zip(looks, rows):
        if ((look["mode"], look["variant"], look["label"]) !=
                (row["picture_mode"], row["variant"], row["label"])):
            raise ValueError("Texture catalog and bank rows differ")
        spatial = look.get("spatial_omitted", {})
        grain, halo, bloom, tint = strengths(spatial)
        effect = spatial.get("effect") or {}
        clarity = 0
        if version == 2 and effect.get("type") == "clarity":
            amount = effect.get("strength")
            if type(amount) is not int or not 1 <= amount <= len(CLARITY_GAIN):
                raise ValueError("Invalid clarity strength")
            clarity = CLARITY_GAIN[amount - 1]
        records.append(ROW.pack(row["picture_mode"], row["variant"], clarity,
                                row["number"], 0, row["table_crc32"],
                                grain, halo, bloom, tint))
    body = b"".join(records)
    return HEADER.pack(f"EP5FXP0{version}".encode("ascii"), version, len(records), len(body),
                       zlib.crc32(body)) + body
