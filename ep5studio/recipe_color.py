"""Bake the point operations from the pinned Caduceus display-sRGB renderer."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen

import numpy as np

from .cube import Cube
from .filmlooks import grid
from .project import atomic_write

REVISION = "78dbbc433ba0d04f1c31376937a98abede881526"
URL = f"https://raw.githubusercontent.com/cakelesscoder/caduceus-ep7/{REVISION}/"
FILES = {
    "webapp/src/preview.ts": "6426202e906f0d43d4089777b1ac504a8621b514361b9c67ce658657376c03d9",
    "webapp/src/pack.ts": "bf57b49c614d3ba24e88c5e361a088331e3ddf03af15bce6aaa465346c067d76",
    "webapp/src/tone.ts": "fe6caa81d151df989768dd9f385233008ef9c5368f81285d67e325f5571c787f",
    "webapp/src/split.ts": "46e3ef75168c07b10bd9dc7019de629a35e64ca424a5d00c7cdad71ac1d1fb65",
    "webapp/src/data/tone_hsm.json": "947686df4865873bd4227e44142c8f0bd168c799108e95c9b1fdb2614e7ec0e7",
    "sim/recipes/library_v2.json": "ecad3ffb50fc34e3ee65e079262e0b6f6e8a90fd0c27ae442a05818b385a6d4c",
}
RECIPES = {"Gold": "lib2_gold", "Portra400": "lib2_portra", "Velvia": "lib2_velvia"}


def _read_reference(root, fetch):
    result = {}
    for name, digest in FILES.items():
        path = Path(root) / name
        if fetch and not path.exists():
            with urlopen(URL + name, timeout=20) as response:
                data = response.read(2_000_000)
            if sha256(data).hexdigest() != digest:
                raise ValueError(f"Invalid downloaded reference: {name}")
            atomic_write(path, data)
        if not path.is_file():
            raise ValueError(f"Missing reference {path}. Use --fetch-reference on first use.")
        data = path.read_bytes()
        # Permit an ordinary Windows Git checkout with CRLF line endings.
        data = data.replace(b"\r\n", b"\n")
        if sha256(data).hexdigest() != digest:
            raise ValueError(f"Reference differs from {REVISION}: {name}")
        result[name] = data
    return result


_RENDER = """
import { readFileSync } from 'node:fs';
import { renderLook } from './preview.ts';
const {recipe, pixels, canvas} = JSON.parse(readFileSync(0, 'utf8'));
const look = {
  kind: 'color', sat: recipe.sat, hue: recipe.hue, light: recipe.light,
  wb: recipe.wb_shift, advice: {contrast: recipe.contrast},
  tone: {blacks: 0, whites: 0, ...recipe.tone},
};
const src = {width: pixels.length, height: 1, data: new Uint8ClampedArray(pixels.length * 4)};
for (let i = 0; i < pixels.length; ++i) src.data.set([...pixels[i], 255], i * 4);
// Leave the original renderer unchanged. A float destination retains its output
// before the canvas's final quantization. The upstream assignment adds 0.5.
const dst = {data: canvas ? new Uint8ClampedArray(src.data.length) : new Float64Array(src.data.length)};
renderLook(src, dst, look, {advice: true, nr: false, grain: 'off'});
const output = Buffer.alloc(pixels.length * 12);
for (let i = 0; i < pixels.length; ++i) {
  for (let c = 0; c < 3; ++c)
    output.writeFloatLE((dst.data[4*i+c] - (canvas ? 0 : 0.5)) / 255, (3*i+c)*4);
}
process.stdout.write(output);
"""


class RecipeReference:
    def __init__(self, root, fetch=False):
        self.files = _read_reference(root, fetch)
        self.recipes = json.loads(self.files["sim/recipes/library_v2.json"])["recipes"]
        self.node = shutil.which("node")
        if not self.node:
            raise ValueError("Install Node.js 24 LTS to run the Caduceus TypeScript renderer.")

    def render8(self, name, pixels, *, canvas=False):
        """Return display RGB from exact 8-bit input coordinates."""
        pixels = np.asarray(pixels)
        if (pixels.ndim != 2 or pixels.shape[1] != 3 or pixels.dtype != np.uint8
                or not 1 <= len(pixels) <= 100_000):
            raise ValueError("Expected 1..100000 RGB8 patches")
        with tempfile.TemporaryDirectory(prefix="ep5-colour-") as tmp:
            folder = Path(tmp)
            (folder / "package.json").write_text('{"type":"module"}', encoding="utf-8")
            for path, source in self.files.items():
                if not path.startswith("webapp/src/"):
                    continue
                relative = path.removeprefix("webapp/src/")
                text = source.decode("utf-8")
                if path.endswith(".ts"):
                    for module in ("pack", "tone", "split"):
                        text = text.replace(f"from './{module}'", f"from './{module}.ts'")
                    text = text.replace("from './data/tone_hsm.json';",
                                        "from './data/tone_hsm.json' with {type:'json'};")
                target = folder / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            runner = folder / "render.mjs"
            runner.write_text(_RENDER, encoding="utf-8")
            data = json.dumps({"recipe": self.recipes[RECIPES[name]],
                               "pixels": pixels.tolist(), "canvas": canvas}).encode()
            result = subprocess.run([self.node, str(runner)], input=data, capture_output=True, timeout=45)
            if result.returncode:
                raise RuntimeError(result.stderr.decode(errors="replace"))
            return np.frombuffer(result.stdout, dtype="<f4").reshape(pixels.shape)

    def cube(self, name):
        """Sample 17 exact normalized grid planes by interpolating adjacent RGB8 patches."""
        coords = grid(17) * 255
        levels = np.unique(np.stack([np.floor(coords[..., 0]), np.ceil(coords[..., 0])])).astype(np.uint8)
        lattice = np.stack(np.meshgrid(levels, levels, levels, indexing="ij"), axis=-1)
        samples = self.render8(name, lattice.reshape(-1, 3)).reshape(lattice.shape)
        low = np.searchsorted(levels, np.floor(coords))
        high = np.searchsorted(levels, np.ceil(coords))
        frac = coords - np.floor(coords)
        values = np.zeros(coords.shape)
        for offset in np.ndindex(2, 2, 2):
            idx = np.where(offset, high, low)
            weight = np.prod(np.where(offset, frac, 1 - frac), axis=-1)
            values += weight[..., None] * samples[idx[..., 0], idx[..., 1], idx[..., 2]]
        return Cube(self.recipes[RECIPES[name]]["name"] + " Reference", 17, np.clip(values, 0, 1))
