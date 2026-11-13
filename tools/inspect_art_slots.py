"""Read-only E-P5 1.8 ART setting, language and chroma table audit. Outputs JSON on stdout."""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.inspect_ep5 import CPU_BASE
from tools.native_probe import MAIN_SHA256, build_probe

LANG_SHA256 = "3841b463195455554ebf0ec80ee7e15c53394e43a54fdc646457b2b7d5b718d8"


def load(path, digest):
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest:
        raise ValueError(f"requires exact factory E-P5 1.8 decoded block: {path}")
    return data


def word(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def language(data, row):
    """Read actual string directory/pointers; these entries do not establish menu reachability."""
    off = word(data, row * 16) - 0x427c0020
    table, end = struct.unpack_from("<II", data, off)
    base = 0xbff2a200
    assert (end - table) // 4 == 2317
    entries = {}
    for i in (*range(60, 70), 582, 583, *range(597, 604), 650, 1717, 1718):
        pos = off + word(data, off + table - base + 4*i) - base
        text = data[pos:pos+256].decode("utf-16-le", errors="surrogatepass").split("\0")[0]
        entries[i] = {"text": text, "utf16_units": len(text.encode("utf-16-le")) // 2,
                      "payload_offset": hex(pos)}
    return entries


def static(main, lang):
    # Unsigned accepted selector range 0x45..0xa8. Table starts at *biased*
    # slot 0x45; instruction operands & scale visible in the following bytes.
    check = main[0x7e229ff0-CPU_BASE:0x7e22a01f-CPU_BASE]
    assert check.hex() == ("8683f8b82843044208a045f1d4f8920cc205cc8f045808fac8a800c305cc8404"
                           "5808fcdc908e477e28bb54f380f0f4")
    cases = defaultdict(list)
    for i in range(69, 169):
        pc = word(main, 0x7e478e90 - CPU_BASE + 4*(i-69))
        cases[pc].append(i)
    groups = []
    for pc, ids in cases.items():
        off = pc - CPU_BASE
        entry = {"mode_ids": ids, "case_pc": hex(pc)}
        if main[off:off+4] == bytes.fromhex("5c 04 fc cc"):
            ptrs = [word(main, off + m.end()) for m in re.finditer(b"\xfc\xcc", main[off:off+65])]
            assert len(ptrs) == 6
            assert [p - ptrs[0] for p in ptrs] == [0, 16, 32, 49, 65, 81]
            entry["pair_rom"] = hex(ptrs[0])
            entry["pair_sha256"] = sha256(main[ptrs[0]-CPU_BASE:ptrs[0]-CPU_BASE+98]).hexdigest()
            # Additional constant references are leads, not a complete caller graph.
            refs = {}
            for p in ptrs:
                matches = [hex(CPU_BASE+m.start()) for m in re.finditer(re.escape(struct.pack("<I", p)), main)
                           if not off <= m.start() < off+68]
                refs[hex(p)] = matches
            entry["other_u32_literal_offsets_cpu"] = refs
        groups.append(entry)
    return {"main_sha256": MAIN_SHA256, "language_sha256": LANG_SHA256, "chroma_switch": groups,
            "language_entries": {"zh-Hans": language(lang, 2), "zh-Hant": language(lang, 3)}}


def summarize_model(main, data):
    writer, routes = data["writer"], data["routes"]
    if [r["mode"] for r in writer] != list(range(256)) or len(routes) != 103*3:
        raise ValueError("incomplete model run")
    peers = defaultdict(list)
    for r in writer:
        if len(r["pointers"]) != 6 or len(r["words"]) != 34:
            raise ValueError("incomplete chroma output")
        peers[tuple(r["pointers"])].append(r["mode"])
    used, handlers = [], {}
    for source, variant, mode, gate, queue in routes:
        if mode == 65535:
            continue
        for fn in queue:
            if fn in handlers:
                continue
            # Find a bounded MOV-immediate operand pointing at this handler's
            # ASCII entry log, independently from the indexed selection tables.
            code = main[fn-CPU_BASE:fn-CPU_BASE+64]
            tags = []
            for m in re.finditer(rb"\xfc[\xcc-\xcf\xdc-\xdf](....)", code, re.S):
                o = word(m[1], 0)-CPU_BASE
                if 0 <= o < len(main):
                    s = main[o:o+96].split(b"\0")[0]
                    if s.startswith(b"art_") and s.endswith(b" in"):
                        tags.append(s.decode("ascii"))
            handlers[fn] = tags
        used.append([source, variant, mode, gate, [hex(x) for x in queue]])
    groups = [{"mode_ids": ids, "pointers": [hex(x) for x in ps],
               "packed_words_sha256": sha256(struct.pack("<34I", *writer[ids[0]]["words"])).hexdigest()}
              for ps, ids in peers.items()]
    return {"fixture": "REC synthetic setting 100..202, variation 1..3, level 200, other flags zero; "
                       "writer separately executed on all 256 mode IDs, zero auxiliary inputs and modeled RAM default",
            "route_columns": ["REC setting", "variation", "packet mode", "ART gate (0=admitted)", "task entries"],
            "runs": len(routes), "non_sentinel_routes": used,
            "handler_entry_strings": {hex(k): v for k, v in handlers.items()}, "writer_alias_groups": groups}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--decoded", type=Path, default=ROOT/"data/ep5-decoded")
    p.add_argument("--native", action="store_true", help="build & execute fixed MN103 model (needs Git/cc)")
    opts = p.parse_args()
    filepath = (opts.decoded/"00_0100_402c0020.decoded.bin").resolve()
    data = load(filepath, MAIN_SHA256)
    result = static(data, load(opts.decoded/"01_0101_427c0020.decoded.bin", LANG_SHA256))
    if opts.native:
        with tempfile.TemporaryDirectory() as tmp:
            exe = build_probe(ROOT/"tools/ep5_art_slots_probe.c", Path(tmp))
            run = subprocess.run([str(exe), str(filepath)], capture_output=True, check=True, timeout=60)
            result["model"] = summarize_model(data, json.loads(run.stdout))
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
