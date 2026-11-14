#!/usr/bin/env python3
"""Static E-P5 portability probe for fishcu/oly_fw_analysis + cakelesscoder/caduceus-ep7.

Read-only. Decodes the local official E-P5 1.8 stock image, then searches for the
structural anchors that the two upstream projects rely on:
  1. OI.Share CGI command table / mcon endpoints (Wi-Fi recipe transfer, no mod needed)
  2. COLOR-profile / HSL machinery (PEN-F style colour wheel)
  3. fileif SD-card file API (Caduceus-style LOOKS.BIN loader)
  4. grain combiner gain tables (110/300/600 + 50/75/100)
  5. hidden log / movie hints, debug shell strings
  6. FF code caves in the main component (where new code could live)
  7. Caduceus edit-signature match rate (port_sigmatch methodology)
Writes a JSON + text report. Never writes firmware.
"""
from __future__ import annotations
import hashlib, json, re, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "external/oly_fw_analysis/tools"))
import oly_container

CPU_BASE = 0x7E101020
STOCK = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
STOCK_SHA = "cc59a4e13b3bf6c46405bd396975cb9c93a7634b7a4a36822259b1fc498b5cfd"
CADUCEUS = ROOT / "build/research/caduceus-ep7-main"

def ascii_strings(data, minlen=4):
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minlen, data):
        yield m.start(), m.group().decode("ascii")

def main():
    stock = STOCK.read_bytes()
    assert hashlib.sha256(stock).hexdigest() == STOCK_SHA, "stock sha mismatch"
    blocks = oly_container.parse(stock)
    main_img = blocks[0].payload
    report = {
        "stock_sha256": STOCK_SHA,
        "components": [{"kind": hex(oly_container.kind(b.header)) if hasattr(oly_container, 'kind') else hex(struct.unpack_from('<H', b.header, 20)[0]),
                         "size": len(b.payload)} for b in blocks],
        "main_size": len(main_img),
        "cpu_base": hex(CPU_BASE),
    }

    strings = list(ascii_strings(main_img))
    report["main_string_count"] = len(strings)

    def find_all(pat):
        rx = re.compile(pat, re.I)
        return [{"off": hex(o), "addr": hex(CPU_BASE + o), "text": t}
                for o, t in strings if rx.search(t)]

    groups = {
        "cgi_commands": r"\.cgi",
        "mcon": r"mcon",
        "oishare": r"oi\.?share|oishare",
        "color_profile": r"COLORTONE|COLOR.?PROFILE|PROFILE",
        "color_creator": r"color.?creator|COLORCREATOR",
        "hsl": r"\bHSL\b|hue.*sat|HSLFX",
        "fileif": r"fileif|FILECLBK|fopen|fread",
        "mount": r"MOUNT|mount ok",
        "sd_paths": r"[A-Z]:\\\\|EP7MOD|DCOLYMP|\.BIN",
        "log_video": r"\blog\b|LOG_|CINE|flat",
        "debug_shell": r"debug|shell|telnet|console",
        "grain": r"grain",
        "picture_modes": r"picture.?mode|PICTURE",
        "art": r"art.?filter|ART_",
        "tone": r"tone.?curve|TONE",
        "wifi": r"wifi|WLAN|192\.168",
        "model": r"E-P5|EP5|E108|PEN",
    }
    hits = {}
    for name, pat in groups.items():
        found = find_all(pat)
        hits[name] = {"count": len(found), "sample": found[:40]}
    report["string_groups"] = hits

    # --- grain gain tables (u16 LE): 110,300,600 and 50,75,100 ---
    grain = {}
    for name, vals in (("combiner31", (110, 300, 600)), ("combiner32", (50, 75, 100))):
        pat = struct.pack("<3H", *vals)
        offs = []
        i = main_img.find(pat)
        while i >= 0 and len(offs) < 8:
            offs.append(hex(CPU_BASE + i))
            i = main_img.find(pat, i + 1)
        grain[name] = offs
    report["grain_gain_tables"] = grain

    # --- FF code caves in main ---
    caves = []
    for m in re.finditer(rb"\xff{512,}", main_img):
        if len(caves) >= 30:
            break
        caves.append({"addr": hex(CPU_BASE + m.start()), "size": m.end() - m.start()})
    report["ff_caves_512plus"] = caves
    report["ff_total_bytes"] = main_img.count(b"\xff" * 1) and sum(m.end() - m.start() for m in re.finditer(rb"\xff{64,}", main_img))

    # --- Caduceus signature match (port_sigmatch method, self-contained) ---
    ep7_main_path = CADUCEUS / "analysis/ep7_1100/00_0100_406a0020.decoded.bin"
    edits_path = CADUCEUS / "releases/v0.32a/edits.json"
    sig = {"ep7_main_present": ep7_main_path.exists(), "edits_present": edits_path.exists()}
    if ep7_main_path.exists() and edits_path.exists():
        ep7 = ep7_main_path.read_bytes()
        EP7_BASE = 0x60020020
        edits = [e for e in json.loads(edits_path.read_text())["edits"] if e["kind"] == "0x100"]
        from collections import Counter, defaultdict
        counts = Counter()
        bygroup = defaultdict(Counter)
        for e in edits:
            a = int(e["addr"], 16) - EP7_BASE
            exp = bytes.fromhex(e["expect"])
            n = len(exp)
            if not (0 <= a < len(ep7)) or ep7[a:a + n] != exp:
                r = "bad-base"
            elif main_img[a:a + n] == exp and a + n <= len(main_img):
                r = "same"
            elif all(b == 0xFF for b in exp):
                r = "absent"
            else:
                r = "absent"
                for c in (32, 16, 8):
                    sigb = ep7[max(0, a - c):a + n + c]
                    i = main_img.find(sigb)
                    if i < 0:
                        continue
                    r = "shifted" if main_img.find(sigb, i + 1) < 0 else "ambig"
                    break
            counts[r] += 1
            bygroup[e.get("why", "?").split()[0].lower().strip(":,")][r] += 1
        tot = len(edits)
        sig["total_edits"] = tot
        sig["counts"] = dict(counts)
        sig["auto_pct"] = round(100.0 * (counts["same"] + counts["shifted"]) / tot, 1) if tot else 0
        sig["by_group"] = {k: dict(v) for k, v in sorted(bygroup.items(), key=lambda kv: -sum(kv[1].values()))[:20]}
    report["caduceus_sigmatch"] = sig

    out = ROOT / "build/research/ep5_portability.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", out)
    print("main size:", len(main_img), "strings:", len(strings))
    for name in groups:
        print(f"{name:16s} {hits[name]['count']:5d}")
    print("grain:", grain)
    print("caves>=512:", len(caves))
    if "auto_pct" in sig:
        print("caduceus auto-match:", sig["auto_pct"], "%", sig["counts"])

if __name__ == "__main__":
    main()
