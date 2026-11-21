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
RELEASE_FILES = {
    "bundles/library_v3.json": "645abaa58f3ebbdeb52428e948fce75825ddd5a5da4a1a5cecd5ada4b16063fd",
    "sim/recipes/library_v3.json": "4b13bd0619f3b1fec9642ebd5c96d42af1157f25155851cb80ff2588f4b06c79",
    "LICENSE": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "NOTICE": "259b24ebda8755f2f7c5c55982f02a2f35beb15b07db6e1c6cc467eb91435873",
}
# UI strings fit the current 6 UTF-16 unit index field. Order comes from the bundle.
LABELS = {
    "velvia": "Velvia", "astia": "Astia", "cl_chrome": "ClChrm", "cl_neg": "ClNeg",
    "provia400": "Prv400", "reala": "Reala", "eterna": "Eterna", "bleach": "Bleach",
    "kchrome": "KChr64", "portra": "Por400", "ektar": "Ekt100", "gold": "Gold",
    "ektachrome": "EkChrm", "cinestill": "CS800T", "pro400h": "Pr400H",
    "aerochrome": "FauxIR", "kchrome25": "KChr25", "portra160": "Por160",
    "fuji200": "Fuji2H", "cuban": "Cuban", "cibachrome": "Ciba", "ultramax": "UMx400",
    "agfa": "Vista", "cs50d": "CS50D", "v250d": "V3250D", "v500t": "V3500T",
    "polaroid": "Polard", "xpro": "XProc", "atrophy": "Atrphy",
}


def _read_reference(root, fetch, files):
    result = {}
    for name, digest in files.items():
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
    def __init__(self, root, fetch=False, *, release=False):
        self.files = _read_reference(root, fetch, FILES | RELEASE_FILES if release else FILES)
        self.recipes = json.loads(self.files["sim/recipes/library_v2.json"])["recipes"]
        self.looks = {name: self.recipes[key] for name, key in RECIPES.items()}
        if release:
            self.recipes.update(json.loads(self.files["sim/recipes/library_v3.json"])["recipes"])
            source_looks = json.loads(self.files["bundles/library_v3.json"])["looks"]
            self.release = {name: self.recipes[row["recipe"]] | row for name, row in source_looks.items()
                            if self.recipes[row["recipe"]]["base"] == "Color Profile"}
            if set(self.release) != set(LABELS):
                raise ValueError("Reference release palette does not match the expected 29 colour looks")
            self.looks.update(self.release)
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
            data = json.dumps({"recipe": self.looks[name],
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
        return Cube(self.looks[name]["name"] + " Reference", 17, np.clip(values, 0, 1))
