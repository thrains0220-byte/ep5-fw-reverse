"""Read normalized 3D .cube tables and compile the E-P5 RGB16LE test format."""
from dataclasses import dataclass
import io
import re

import numpy as np


MAX_BYTES = 32 * 1024 * 1024
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_HEADERS = {"LUT_3D_SIZE", "DOMAIN_MIN", "DOMAIN_MAX", "LUT_3D_INPUT_RANGE"}


@dataclass(frozen=True, eq=False)
class Cube:
    title: str
    side: int
    values: np.ndarray  # [blue, green, red, output channel]

    def __post_init__(self):
        if type(self.side) is not int or not 2 <= self.side <= 65 or not isinstance(self.title, str):
            raise ValueError("invalid Cube title or grid size")
        arr = np.asarray(self.values)
        if (arr.shape != (self.side, self.side, self.side, 3) or arr.dtype.kind not in "fui"
                or not np.isfinite(arr).all() or arr.min() < 0 or arr.max() > 1):
            raise ValueError("Cube requires a finite normalized [B,G,R,3] grid")
        # A read-only *view* would still let the caller mutate its underlying input.
        frozen = np.frombuffer(arr.astype(np.float64, copy=False).tobytes(), dtype=np.float64)
        object.__setattr__(self, "values", frozen.reshape(arr.shape))


def parse_cube(text: str | bytes) -> Cube:
    """Parse one 2..65 normalized 3D table. No colour-space conversion is implied."""
    if not isinstance(text, (str, bytes)):
        raise TypeError("cube input must be text or UTF-8 bytes")
    if len(text) > MAX_BYTES or (isinstance(text, str) and len(text.encode("utf-8")) > MAX_BYTES):
        raise ValueError(".cube exceeds 32 MiB")
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig")
    else:
        text = text.removeprefix("\ufeff")
    title, side, index = "", 0, 0
    seen, rows = set(), None
    for number, line in enumerate(io.StringIO(text, newline=None), 1):
        def fail(reason):
            raise ValueError(f"line {number}: {reason}")
        if len(line) > 4096:
            fail("overlong .cube line")
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key = line.split(None, 1)[0]
        if key == "TITLE":
            if key in seen or index:
                fail("duplicate or late TITLE")
            title_match = re.fullmatch(r'TITLE\s+"([^"\x00-\x1f]*)"\s*(?:#.*)?', line)
            if not title_match:
                fail('expected TITLE "name"')
            title = title_match[1]
            seen.add(key)
            continue
        fields = line.partition("#")[0].split()
        key = fields[0]
        if key.startswith("LUT_1D_"):
            fail("1D tables and combined 1D shaper + 3D tables are unsupported")
        if key in _HEADERS:
            if key in seen or index:
                fail(f"duplicate or late header {key}")
            seen.add(key)
            if key == "LUT_3D_SIZE":
                if (len(fields) != 2 or not re.fullmatch(r"[0-9]{1,2}", fields[1])
                        or not 2 <= int(fields[1]) <= 65):
                    fail("LUT_3D_SIZE must be an integer from 2 through 65")
                side = int(fields[1])
                rows = np.empty((side**3, 3), dtype=np.float64)
            else:
                if "LUT_3D_INPUT_RANGE" in seen and seen & {"DOMAIN_MIN", "DOMAIN_MAX"}:
                    fail("use DOMAIN_MIN/MAX or LUT_3D_INPUT_RANGE, not both")
                expected = [0, 1] if key == "LUT_3D_INPUT_RANGE" else [int(key == "DOMAIN_MAX")] * 3
                if (len(fields)-1 != len(expected) or not all(_NUMBER.fullmatch(v) for v in fields[1:])
                        or [float(v) for v in fields[1:]] != expected):
                    fail("only the normalized [0,1] input domain is supported")
            continue
        if not _NUMBER.fullmatch(key):
            fail(f"unknown header or invalid number: {key[:40]}")
        if rows is None or len(fields) != 3 or not all(_NUMBER.fullmatch(v) for v in fields[1:]):
            fail("expected one RGB triplet after LUT_3D_SIZE")
        if index == len(rows):
            fail("too many data rows")
        triplet = tuple(map(float, fields))
        if not all(0 <= v <= 1 for v in triplet):
            fail("RGB outputs must be finite and within [0,1]")
        rows[index] = triplet
        index += 1
    if rows is None or index != len(rows):
        raise ValueError(f"expected {side**3} data rows after LUT_3D_SIZE, got {index}")
    return Cube(title, side, rows.reshape(side, side, side, 3))


def sample_cube(cube: Cube, rgb: np.ndarray) -> np.ndarray:
    """Trilinearly interpolate a normalized float RGB array of any leading shape."""
    if not isinstance(cube, Cube):
        raise TypeError("expected Cube")
    if (not isinstance(rgb, np.ndarray) or rgb.dtype.kind != "f" or rgb.ndim < 1
            or rgb.shape[-1] != 3 or not np.isfinite(rgb).all()
            or np.any(rgb < 0) or np.any(rgb > 1)):
        raise ValueError("expected finite float RGB array [...,3] in [0,1]")
    flat = rgb.reshape(-1, 3)
    dest = np.empty(flat.shape, dtype=np.float64)
    for start in range(0, len(flat), 65536):
        coord = flat[start:start+65536].astype(np.float64, copy=False) * (cube.side - 1)
        cell = np.minimum(coord.astype(np.intp), cube.side - 2)
        frac = coord - cell
        r, g, b = cell.T
        fr, fg, fb = (v[:, None] for v in frac.T)
        def plane(b):
            lo = cube.values[b, g, r] * (1-fr) + cube.values[b, g, r+1] * fr
            hi = cube.values[b, g+1, r] * (1-fr) + cube.values[b, g+1, r+1] * fr
            return lo * (1-fg) + hi * fg
        dest[start:start+len(cell)] = plane(b) * (1-fb) + plane(b+1) * fb
    return dest.reshape(rgb.shape)


def compile_rgb17(cube: Cube) -> bytes:
    if not isinstance(cube, Cube):
        raise TypeError("expected Cube")
    if cube.side == 17:
        sampled = cube.values  # exact legacy round-to-even, no resampling round-off
    else:
        b, g, r = np.indices((17, 17, 17), dtype=np.float64)
        sampled = sample_cube(cube, np.stack((r, g, b), axis=-1) / 16.0)
    return np.rint(sampled * 65535).astype("<u2").tobytes()
