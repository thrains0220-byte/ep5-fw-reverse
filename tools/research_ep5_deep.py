#!/usr/bin/env python3
"""Second-pass E-P5 portability probe: CGI surface, colour tables, debug shell, grain combiners.
Read-only; writes build/research/ep5_deep.json. Never writes firmware."""
from __future__ import annotations
import hashlib, json, re, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "external/oly_fw_analysis/tools"))
import oly_container

CPU_BASE = 0x7E101020
STOCK = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"

def main():
    stock = STOCK.read_bytes()
    blocks = oly_container.parse(stock)
    m = blocks[0].payload
    rep = {}

    # 1. CGI command list block around 0x7ec26779
    a = 0x7ec26779 - CPU_BASE
    seg = m[a - 0x400:a + 0x1800]
    cgis = [(hex(CPU_BASE + a - 0x400 + mm.start()), mm.group().decode())
            for mm in re.finditer(rb"[\x20-\x7e]{4,}", seg)]
    rep["cgi_region"] = cgis

    # 2. colour-related property names near COLORTONE enum + saturation/hue/sharpness
    pats = {
        "saturation": rb"[Ss]aturation",
        "hue": rb"\bhue\b|Hue",
        "sharpness": rb"[Ss]harpness",
        "contrast": rb"[Cc]ontrast",
        "graduation": rb"[Gg]radation|gradation",
        "colorcreator": rb"COLOR_CREATOR|ColorCreator|color_creator",
        "picturemode_props": rb"colortone|colorTone|ColorTone",
        "wbshift": rb"wb.?shift|WBShift|amber|AMBER",
        "keepcolor": rb"keep.?color|partial.?color",
    }
    out = {}
    for name, pat in pats.items():
        hits = []
        for mm in re.finditer(pat, m):
            s = mm.start()
            # extend to full printable string
            lo = s
            while lo > 0 and 32 <= m[lo - 1] <= 126:
                lo -= 1
            hi = mm.end()
            while hi < len(m) and 32 <= m[hi] <= 126:
                hi += 1
            txt = m[lo:hi].decode()
            if len(hits) < 25:
                hits.append({"addr": hex(CPU_BASE + lo), "text": txt[:120]})
        out[name] = hits
    rep["colour_strings"] = out

    # 3. debug shell / SD debug switch (PEN-F WIFI_DEBUG analog)
    dbg = []
    for pat in (rb"debug.{0,24}(shell|mode|switch|flag)", rb"telnet", rb"port.?23",
                rb"WFDP|WFCL", rb"debug\.txt|DEBUG\.TXT|\.dbg|DBGFILE", rb"shell"):
        for mm in re.finditer(pat, m, re.I):
            lo = mm.start()
            while lo > 0 and 32 <= m[lo - 1] <= 126:
                lo -= 1
            hi = mm.end()
            while hi < len(m) and 32 <= m[hi] <= 126:
                hi += 1
            dbg.append({"addr": hex(CPU_BASE + lo), "text": m[lo:hi].decode()[:140]})
            if len(dbg) > 120:
                break
    rep["debug_strings"] = dbg[:120]

    # 4. grain gain tables as u32 too, and mask curve signature (0..36 zeros then 1023)
    grain = {}
    for name, vals, fmt in (("g31_u16", (110, 300, 600), "<3H"),
                            ("g32_u16", (50, 75, 100), "<3H"),
                            ("g31_u32", (110, 300, 600), "<3I"),
                            ("g32_u32", (50, 75, 100), "<3I")):
        pat = struct.pack(fmt, *vals)
        offs, i = [], m.find(pat)
        while i >= 0 and len(offs) < 6:
            offs.append(hex(CPU_BASE + i))
            i = m.find(pat, i + 1)
        grain[name] = offs
    # grain mask curve: 37 halfword zeros then 1023 (0x03ff) repeated
    mask = struct.pack("<H", 0) * 37 + struct.pack("<H", 1023) * 4
    offs, i = [], m.find(mask)
    while i >= 0 and len(offs) < 6:
        offs.append(hex(CPU_BASE + i))
        i = m.find(mask, i + 1)
    grain["mask_curve_37z_1023"] = offs
    rep["grain"] = grain

    # 5. ART effect name strings (what the E-P5 actually ships)
    arts = []
    for mm in re.finditer(rb"COLORTONE_[A-Z_]+", m):
        arts.append(mm.group().decode())
    rep["colortone_enum"] = sorted(set(arts))

    # 6. mcon cgi hidden endpoints
    mcon = []
    for mm in re.finditer(rb"(get|set)_mcon[a-z_]*\.cgi", m):
        mcon.append({"addr": hex(CPU_BASE + mm.start()), "text": mm.group().decode()})
    rep["mcon_cgi"] = mcon

    # 7. firmware model/version strings
    ver = []
    for mm in re.finditer(rb"(E-?P5|EP5|E108|1\.8|Ver\.? ?1\.[0-9])[^\x00]{0,40}", m):
        t = mm.group()
        if all(32 <= b <= 126 for b in t):
            ver.append({"addr": hex(CPU_BASE + mm.start()), "text": t.decode()[:80]})
        if len(ver) > 40:
            break
    rep["version_strings"] = ver[:40]

    outp = ROOT / "build/research/ep5_deep.json"
    outp.write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", outp)
    print("cgi region entries:", len(cgis))
    print("mcon cgi:", mcon)
    print("grain:", grain)
    print("colortone enum:", rep["colortone_enum"])

if __name__ == "__main__":
    main()
