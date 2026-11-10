# E-P5 offline integration implementation plan

> Execute inline. The user asks to finish as much as possible before connecting the camera; earlier authorization waives another design approval round.

**Goal:** deliver a bounded processing engine and reproducible camera evidence collector so hardware work starts with usable code, not scaffolding.

**Architecture:** keep the portable C colour engine independent of camera addresses. Normalize a captured native descriptor only against a separately supplied, bounded memory mapping. Process Y0 Cb Y1 Cr pairs using 16-bit RGB LUT sampling and residual colour changes, preserving full image dimensions and identity bytes. Compile and execute that exact engine as MN103 instructions. Collect only native read-only HTTP evidence when the user connects later.

**Stack:** existing C99, Python standard library, local MN103 GCC and pinned CPU engine. Work on existing work/ep5-film branch; no new worktree or dependency is needed.

## Global constraints and review focus

- Preserve ORF; no RAW writes, JPEG decoder/encoder substitution or image resizing.
- Camera is unavailable and runs an unknown modified image. Do not fabricate a flashable package or firmware insertion addresses.
- E-P5's native descriptor debug routine at 0x7e40fba4 reads addresses at +0/+4, format at +8 and u16 geometry at +10..+26; establish its fields by original-instruction execution.
- Format 0x302 as YUYV and full-range BT.601 are explicit integration hypotheses, not established E-P5 colour semantics. Adapter requires an explicit encoding selection.
- Invalid dimensions, LUT size, amount and mapped extents must fail before image changes. Stride padding and neighboring memory must survive.
- Identity LUT and zero amount must preserve bytes, including saturated YCC outside the RGB cube. Nonidentity processing uses 16-bit RGB internally and pair-averaged chroma deltas.
- Cancellation after changes requires discarding/redeveloping the working YCC buffer; never authorize encoding a partially processed image.
- Network collection accepts a numeric private/local IPv4 host, disables proxies and redirects, uses GET allowlists and byte/time limits, verifies E-P5 identity first, never switches networks or writes to the camera.
- Camera responses/samples stay in ignored sessions/ with private permissions. Existing destination files must not be overwritten.

## Task 1: native descriptor evidence and portable processing

Files: firmware/lut.[ch], firmware/film.[ch], tools/ep5_image_probe.c, tools/image_probe.py, tests/test_film.py, tests/test_image_probe.py.

- [x] Write failing tests for descriptor ranges/cropping, identity/extreme chroma, independent reference colour output, strength, full-size padded image, cancellation and invalid-input nonmutation.
- [x] Add shared RGB16 LUT sampling while keeping RGB8 API behavior.
- [x] Implement descriptor normalization and full-range BT.601 YUYV processing with bounded row progress/cancellation; return a distinct discard result after partial work.
- [x] Execute the original descriptor logger with synthetic read-only descriptor and modeled log sinks. Record actual field offsets, labels, call frame and preserved registers/stack; do not model image conversion.
- [x] Run host tests and retain original-code evidence.

## Task 2: target engine execution

Files: tools/check_mn103_lut.py, tests/fixtures/film_target.c, tests/test_mn103_lut.py.

- [x] Extend failing target tests to the production film engine, descriptor normalization and cancellation.
- [x] Compile unchanged engine and a test-only GCC caller, reject AM33 instructions, run bounded target buffers against host results. Keep RGB8 verification working.
- [x] Record binary size, source hashes, cases and the hardware contracts still missing.

## Task 3: ready-to-run camera evidence collection

Files: tools/camera_collect.py, tests/test_camera_collect.py, docs/WIFI_READONLY.md, README.md.

- [x] Test against a local HTTP fixture: exact GET sequence, E-P5 identity, no redirect/proxy, size limit, malformed XML, safe DCIM paths, download integrity and no overwrite.
- [x] Implement bounded collection of caminfo/commands/connectmode/DCIM listing and optional explicitly named original ORF/JPEG files into a new private session directory.
- [x] Document one invocation for later connection and the remaining native hook/cache/residency/recovery work, distinguishing tested software from unverified hardware.
- [x] Full suite, independent review and meaningful fixes; evidence retained in docs/offline-integration-verification.json.
- [ ] Commit and sync the already authorized GitHub feature branch.

## Decisions and results

Ruling: implement an explicit YUYV/BT.601-full adapter without silently selecting it for the camera — it provides a usable, tested candidate while keeping unknown encoding visible; an E-P5 buffer capture may require another adapter.

Ruling: a resident loader and flash package require resolved E-P5 code residency, cache, scheduling and recovery contracts. Finish the portable entry and collector first, and document exact unresolved dependencies rather than implement a loader that assumes other models' addresses.

Result: native descriptor reader executes 58 instructions and matches all 13 field markers with its original frame. RGB8 target 853 bytes/7 cases; film target 2,567 bytes/17 cases, all target/host outputs match. Host full-resolution YUYV and existing RGB8 checks pass. Final suite: 39 tests, no skips, 28.690 seconds.

Review: isolated independent first suite 38 passed; reviewer found an important per-read/absolute-timeout mismatch and a minor XML encoding rejection bypass. Slow-drip regression first failed, then passed with per-recv absolute deadlines. UTF-16 BOM and BOM-less LE/BE regressions first failed, then passed with strict UTF-8 decoding and NUL rejection. Reviewer confirmed fixes and reported no outstanding findings. Hardware encoding, hook/cache/residency/watchdog/save/recovery remain unqualified; no minor findings deferred.
