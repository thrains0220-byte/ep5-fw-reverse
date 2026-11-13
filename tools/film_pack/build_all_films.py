"""Build and verify every native film look pack (Windows Python, has numpy)."""
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

LABELS = {
    "gold200": ("柯达金200", "柯達金200"),
    "portra160": ("人像160", "人像160"),
    "velvia50": ("浓艳反转50", "濃豔反轉50"),
    "classicchrome": ("经典铬", "經典鉻"),
    "ektar100": ("风景100", "風景100"),
    "bleach": ("漂白银留", "漂白銀留"),
    "moriyama_bw": ("森山黑白", "森山黑白"),
    "trix_bw": ("TriX黑白", "TriX黑白"),
}
STOCK = "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
for key, (zh, zht) in LABELS.items():
    out = ROOT / f"build/film-{key}"
    if out.exists():
        print(f"{key}: exists, skip build")
    else:
        r = subprocess.run([sys.executable, "tools/build_native_film_pack.py", STOCK,
                            "--look", key, "--label-zh", zh, "--label-zht", zht,
                            "--out", str(out)], cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            print(f"{key}: BUILD FAIL\n{r.stderr[-800:]}"); continue
        print(r.stdout.strip().splitlines()[0])
print("=== build done ===")
