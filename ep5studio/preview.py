"""Desktop RGB preview of the E-P5 experimental 17³ sampler (not the native ISP)."""
import numpy as np

from .cube import Cube, sample_cube


def preview_rgb8(pixels: np.ndarray, table: bytes, amount_q8: int = 256) -> np.ndarray:
    """Mirror lut.c's interpolation and film.c's signed Q8 delta on RGB8."""
    if (not isinstance(pixels, np.ndarray) or pixels.dtype != np.uint8 or pixels.ndim != 3
            or pixels.shape[2] != 3 or min(pixels.shape[:2]) < 1):
        raise ValueError("expected a nonempty uint8 RGB image [H,W,3]")
    if not isinstance(table, bytes) or len(table) != 17**3 * 6:
        raise ValueError("expected a 29478-byte RGB16LE LUT")
    if type(amount_q8) is not int or not 0 <= amount_q8 <= 256:
        raise ValueError("strength must be an integer from 0 through 256")
    if amount_q8 == 0:
        return pixels.copy()
    lut = np.frombuffer(table, dtype="<u2").reshape(17,17,17,3)
    src = pixels.reshape(-1, 3)
    dest = np.empty(src.shape, dtype=np.uint8)
    for start in range(0,len(src),65536):
        rgb16 = src[start:start+65536].astype(np.int64) * 257
        pos = rgb16 * 16
        cell = np.minimum(pos // 65535, 15)
        r,g,b = cell.T
        fr,fg,fb = (v[:,None] for v in (pos - cell*65535).T)
        def lerp(a, b, f):
            return (a*(65535-f) + b*f + 32767) // 65535
        def plane(b):
            return lerp(lerp(lut[b,g,r], lut[b,g,r+1], fr),
                        lerp(lut[b,g+1,r], lut[b,g+1,r+1], fr), fg)
        out = lerp(plane(b),plane(b+1),fb)
        if amount_q8 != 256:
            delta = (out-rgb16) * amount_q8
            out = rgb16 + np.sign(delta) * ((np.abs(delta) + 128) // 256)
        dest[start:start+len(out)] = (out+128) // 257
    return dest.reshape(pixels.shape)


def resample_report(cube: Cube, table: bytes) -> dict:
    """Measure the table against the source at fixed RGB8 locations (including endpoints)."""
    if not isinstance(cube, Cube):
        raise TypeError("expected Cube")
    n = max(33, cube.side)
    levels = np.rint(np.linspace(0,255,n)).astype(np.uint8)
    b,g,r = np.meshgrid(levels,levels,levels,indexing="ij")
    samples = np.stack((r,g,b),axis=-1).reshape(n*n,n,3)
    preview = preview_rgb8(samples,table)
    ideal = np.rint(sample_cube(cube,samples.astype(np.float64)/255.0)*255.0)
    diff = np.abs(preview.astype(np.float64) - ideal)
    return {"metric": "source cube vs RGB8 preview of compiled 17-grid table",
            "sample_grid_side": n, "sample_count": n**3,
            "max_rgb8_error": int(diff.max()), "mean_rgb8_error": float(diff.mean()),
            "camera_calibrated": False}
