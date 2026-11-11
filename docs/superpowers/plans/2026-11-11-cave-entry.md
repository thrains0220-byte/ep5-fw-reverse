# E-P5 cave-resident colour entry plan

> Execute inline under the user's existing implementation authorization. The target remains a flashable in-camera film firmware. This stage resolves link layout and native ABI integration; it does not qualify camera memory ownership or publish an upgrade file.

**Goal:** compile our original colour engine and one LUT into the exact E-P5 code-space candidate identified in OM-C, and execute the patched original ART caller → new code → native JPEG call in the bounded CPU model.

**Architecture:** original sources only, with fixed E-P5 1.8 baseline and address/byte guards. A small assembly entry preserves the incoming registers/MDR, calls a GCC C adapter and recreates the original codec call/frame/continuation. No heap, BSS or writable module state. A read-only control record defaults to disabled; only the CPU test supplies a synthetic buffer qualification record. The real image format, cache, watchdog, producer/lifetime and duplicate-processing policy remain unqualified.

**References:** docs/OM_C_DBV040_REVIEW.md, docs/FLASHABLE_PRODUCT.md. OM-C tag 9165af1 contains README only; its downloaded binary metadata supplies independently verified address facts, not reused source/payload.

## Scope and interfaces

- Existing checkout work/ep5-film; user has requested continuing in this project. Reuse local toolchain, film/lut C, pinned CPU engine and native ART builder evidence.
- Create firmware/ep5_art_entry.S, firmware/ep5_art_entry.c, firmware/ep5_art_entry.ld; new build/check tool tools/cave_entry.py and bounded runner tools/ep5_cave_probe.c; tests/test_cave_entry.py.
- Entry linked at 0x7e128010, end <=0x7e130000 (32,752 bytes). LUT is fixed 17³ RGB16, 29,478 bytes. Linker rejects excess size, data/BSS, unresolved services or AM33-only decoding.
- Native site 0x7e3ed8d1 has bytes cd b3 6f f0 10. Model-only replacement is a 5-byte relative JMP; entry calls 0x7e3f4884 with [d2,d3,a2,a3],16 and resumes 0x7e3ed8d6. Never use the other project's aperture hooks.
- Control record: six little-endian u32: tag 0x43355045, enabled, map_start, map_bytes, encoding, amount. Defaults: tag set, all other fields zero. No CLI enabling a camera build.
- Adapter accepts only independently mapped complete duplicated geometry (request u16 at +4/+6 equals +8/+10), no resize flag at request+36 bit1, bounded even width, height, encoding/strength. It does not infer plane order or size from an arbitrary pointer. Reject module/request overlap. Unknown/disabled controls bypass processing and retain native codec behavior.
- Success uses exact existing ep5_film_apply(..., NULL, NULL). There is no cooperative scheduling or cancellation hook in this candidate; those cannot be claimed until actual task services are known.
- Report/output are a relocatable candidate at fixed addresses plus a model patch manifest, explicitly non-installable. Do not emit an E1089999.BIN or whole upgraded image.

## Tasks

- [x] Test first: exact baseline/FF/hook guards, no overwrite and link bounds; default record disabled and no AM33 instructions. Compile actual core, table and assembly entry.
- [x] Test first: original native builder runs through JMP into actual compiled code, host/target pixels match, native request/context/registers/MDR/SP and codec return are preserved. Logger/codec only are modeled services; no host service computes pixels.
- [x] Cover disabled, identity, warm, partial strength, invalid capacity/encoding/amount, null/wrong mapping, nonduplicated geometry and native resize flag; invalid cases must leave pixels intact.
- [x] Record the real binary layout and source hashes, run full suite, independent review and meaningful fixes.
- [x] Document unresolved camera contracts and source provenance; commit and sync the authorized GitHub branch.

## Review focus

The native call frame and continuation must survive the GCC boundary. Buffer size and arithmetic must reject before mutation, including mapped-range wrap and writable image overlap with code/request. Default must not touch a pixel. Test fixture must patch the actual instruction bytes, not replace the native builder or pixel algorithm with a host model. A candidate fitting the cave is not proof the cave stays free or is resident on physical boot.

## Decisions/results

Ruling: use one compiled original LUT and a disabled qualification record — proves the tight body-specific layout/ABI step without presuming the unresolved camera buffer contract; it does not yet deliver a selectable camera effect.

Result: complete module 31,126 bytes, spare 1,626, readonly control24 and LUT29,478. Fifteen native cases pass; warm/half cases execute69,345 instructions for80 pixels and match host, default-disabled143. Native frame preservation includes the pre-call MDR and relocated CALL return-address semantics. The initial test mistakenly compared codec-entry MDR with the pre-CALL value; observed native instruction semantics required separate before-call/at-codec assertions. Veneer also reserves GCC's return slot plus8-byte argument flushback area per the local compiler ABI.

Verification:43 tests, no skips,32.691 seconds. Independent isolated review rebuilt31,126-byte module and passed all3 new tests/15cases; no actionable findings reported. No physical camera work, default-enabled build, wholefirmware update, cache/task qualification or JPEG encoder execution was performed. Evidence:docs/cave-entry-verification.json; source/limits:docs/CAVE_ENTRY.md.
