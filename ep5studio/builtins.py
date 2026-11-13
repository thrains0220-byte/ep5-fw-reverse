"""Original test and film-genre looks, with no third-party film assets or vendor data."""
import struct


def default_cubes():
    from tools.compile_lut import warm_negative
    from .filmlooks import LOOK_SPECS, build_cube, cube_text
    identity = [(r / 16, g / 16, b / 16) for b in range(17) for g in range(17) for r in range(17)]
    values = struct.unpack("<14739H", warm_negative())
    warm = [tuple(v / 65535 for v in values[i:i+3]) for i in range(0, len(values), 3)]
    for name, title, rows in (("Identity.cube", "恒等校验", identity),
                              ("WarmNegative.cube", "暖调负片（实验）", warm)):
        header = f'TITLE "{title}"\n# Original project look, not measured film-stock reproduction\nLUT_3D_SIZE 17\n'
        yield name, (header + "\n".join(" ".join(f"{v:.10f}" for v in row) for row in rows) + "\n").encode("utf-8")
    for name, _title, _fn, _note in LOOK_SPECS:
        if name == "Identity":
            continue
        cube, note = build_cube(name)
        yield name + ".cube", cube_text(cube, note)
