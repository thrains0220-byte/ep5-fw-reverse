# E-P5 Pre-Cable Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** prepare the reproducible, read-only USB sample intake and one default-off picture-parameter experiment so connection time can focus on E-P5 evidence rather than tooling.

**Architecture:** reuse the existing stock-hash-guarded cave module for a separate experimental control value (`2`) that changes only the ART packet contrast byte for one exact mode/geometry at the native send call. Reuse the existing JPEG/ORF signature and JPEG dimension checks for explicit files copied from USB Storage; never send camera commands or generate an update container in this stage.

**Tech Stack:** Python standard library, freestanding C, MN103 assembly/compiler, pinned bounded CPU runner.

**Spec:** `docs/superpowers/specs/2026-11-11-ep5-film-project-plan.md` (T1–T4, route A).

## Global Constraints

- Target only official E-P5 1.8 main block SHA-256 `dfe255e4d5a43329712c1fdfd6861ee1f3ef54a268b6096628bf045d8cc590df`.
- Preserve default-disabled control, non-installable build and existing LUT route (`control[1]=1`).
- The parameter probe uses `control[1]=2`, exact mode 105/variant 1, 4:3 full geometry, neutral source contrast, and only packet byte `+157 → 1`.
- The fixed global ART packet's task ownership and the color effect on saved JPEG remain unproven; the probe is not a release build.
- USB Storage intake reads explicitly selected files only, leaves originals untouched, and stores copied originals plus SHA-256, size and dimensions under a private new session directory.

## Review Focus

- MN103 call frame and original send function arguments/return after the new veneer.
- The mode, variant, geometry and original-value gates; no mutation in disabled/LUT/other configurations.
- Firmware cave layout and original-byte guard, including no camera update file.
- USB path validation, symlink handling, failed copy cleanup and source preservation.
- Static/model evidence boundaries in docs.

## Task 1: USB Storage sample intake

- [ ] Add failing tests in `tests/test_usb_collect.py` for explicit ORF/JPEG copy, private manifest, full-size JPEG header, existing destination, bad source signatures, traversal/symlink and size limits. Run `python3 -m unittest tests.test_usb_collect -v`; expected: import or behavior failures.
- [ ] Implement minimal `tools/usb_collect.py` with `--source`, `--out`, repeated `--file` paths validated by `camera_collect.validate_file`. Copy via `.part`, hash while streaming, validate before final rename, and write a complete/incomplete manifest. Run focused tests; expected: all pass.
- [ ] Add the USB Storage invocation and its limits to `docs/CAMERA_INTEGRATION.md`. Run the full suite; expected: all pass.
- [ ] Commit Task 1 with the tests and documentation.

## Task 2: Disabled route-A parameter probe

- [ ] Add failing builder/runner tests for a fourth old-byte-guarded call site at `0x7e3ed835`, default-disabled layout, and exact-mode one-byte mutation while original send ABI and return survive. Run focused tests; expected: fail for the absent hook.
- [ ] Add a small veneer in `firmware/ep5_art_entry.S` and a guarded C probe in `firmware/ep5_art_entry.c`, preserving the original `0x7e3fca97` call at its native frame. Extend `firmware/ep5_art_entry.ld` and `tools/cave_entry.py` with the new original-byte guard and manifest entry.
- [ ] Add a bounded native runner or extend the existing runner to execute the stock send call site with synthetic packet/context and modeled queue destination. Cover enabled, disabled, wrong mode/variant/geometry/value, and ABI/return. Run focused and full suite; expected: all pass.
- [ ] Record exact evidence and open contracts in `docs/CAVE_ENTRY.md` and `docs/FINDINGS.md`; do not create a camera update package. Commit Task 2.

## Task 3: Connected-session handoff

- [ ] Write one concise `docs/CONNECT_DAY.md` with the actual USB Storage capture command, required ORF/JPEG controls, first read-only checks, and separate later install/recovery gates. Cite the official E-P5 manual for Storage behavior.
- [ ] Re-run full suite, build/manifest validation, exact-stock hashes and `git diff --check`; expected: no failures and no installable artifact.
- [ ] Request one fresh whole-change code review, fix material issues, then sync the feature branch authorized by the user.
