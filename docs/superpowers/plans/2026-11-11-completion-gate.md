# E-P5 completion-qualified colour entry plan

> Execute inline with executing-plans and test-driven-development. Existing user authorization covers implementation and syncing work/ep5-film. Spec: docs/FLASHABLE_PRODUCT.md.

**Goal:** require an observed matching ART completion before modifying pixels, consume that qualification once, and verify the native release ordering.

**Architecture:** keep the existing JPEG entry and disabled control record. Add guarded veneers at the stock ART receive and release calls, execute the original functions with native frames, validate the reply, and publish context/buffer qualification in eight explicitly reserved uncached bytes. JPEG entry consumes matching qualification; release clears unused qualification. No heap, files, menu redesign or enabled firmware container.

**Scope:** firmware/ep5_art_entry.S/.c/.ld, tools/cave_entry.py, tools/ep5_cave_probe.c, tests/test_cave_entry.py; native timing evidence/docs. Reuse original compiler/CPU helpers.

## Requirements and review focus

- Guard all three exact native call instructions; total module including LUT/state must fit32752 bytes.
- Default disabled control must not change pixels or state. State storage exactly8 initialized bytes, uncached symbol alias; no other writable module regions.
- Only wrapper result0, reply u16 status0, token1 and packet0x605f4510 qualify; buffer getter's nonzero address and original a3 context are associated. Poison reply fields before receiving because the wrapper discards kernel byte count. This is a narrow protocol candidate, not proof all camera replies follow it.
- Preserve native receiver arguments, return value, GPR/MDR/SP semantics and caller continuation; GCC third argument requires stack slot12.
- No completion, short/failed receive, failure reply, wrong token/packet/context or a second JPEG attempt must leave pixels untouched. Existing invalid mapping/encoding/capacity guards remain.
- Actual queue/ISP/cache/concurrency and long-running work are unmodeled; do not claim model success means flashable.

## Tasks

- [x] RED: extend module/default layout and native cases with completion/duplicate/release assertions; observe failures.
- [x] Implement receive/release veneers, bounded qualification state and consuming JPEG guard; execute original receive-tail and JPEG builder around real compiled module.
- [x] Trace original outer caller/release and document precisely which sequence was executed versus statically inspected.
- [x] One fresh review and meaningful fixes, including regression/mutation checks.
- [x] Archive final whole-suite evidence, commit and sync.

## Decisions/results

Ruling: qualify on an explicit matching completion rather than entry into JPEG — rec_art_exec returns its send status after waiting and does not inspect the received status in the traced instructions. Without this guard, request geometry alone can authorize processing after a modeled error reply. Cost if the response protocol assumption is wrong: processing bypasses; the firmware remains disabled pending actual queue qualification.

Native trace correction: original OlyQeRd0x7e131208 translates nonnegative kernel byte counts into success0, not12. Moved the probe boundary down to kernel receive0x7e117c7c, executing both original wrappers; changed C qualification to status0 and poisoned all12 reply bytes before receiving. A partial8-byte kernel reply now returns wrapper0 but retains an invalid packet field and bypasses colour. The original rec_art_exec tail still returns its send status0 after receive failure, showing why the guard is needed.

Release refinement: reserve a third hook at0x7e3f2476 to clear unconsumed state before original rec_art_release0x7e3edac1. Fault scenario releases before JPEG and reuses the same synthetic address without a new completion; pixels must remain unchanged. Physical scheduler interleaving remains unqualified.

Regression: mapping the uncached code alias initially caused an attempted write tobe128010 and failed the bounded runner. Reject both cached and uncached cave ranges before colour, preserving read-only code/LUT/state ownership.

Final review: the reviewer independently mutated away poisoning and buffer matching; initial zero-filled fixtures did not catch either. Seed a valid stale12-byte response at the actual native call site and add8/11-byte cases; vary the buffer between completion and JPEG. Both mutations now fail at the corresponding short_reply/wrong_buffer pixel comparisons. No tracked source was mutated; private source copies were compiled.

Final review: reproduced request-alias overlap with stack60000000 mirrored ata0000000, returning to corrupted PC6603050a. Added request-alias regression RED→GREEN; reject both views only within the6/7 and a/b DRAM windows and reject a request spanning the window boundary. The arbitrary low model stack was moved into that actual alias family so the guard is exercised.

Final review: kernel -50 maps to -2 in the original wrapper. Corrected the probe expectation and added receive_timeout; corrected evidence/header to state original receiver execution and all three veneers. These improve verification accuracy and were handled with the other important fixes; no deferred minor findings.

Reviewer declined physical boot/cache/ISP/queue concurrency/encoding/ORF judgement and identified cross-job reply freshness as open: fixed token/packet lack a per-job nonce, and sampled current context/buffer are not echoed identities. Ruling: preserve this as an explicit unresolved requirement; keep module disabled, rather than claim universal duplicate/replay prevention. Wrong assumption here could process an unfinished frame, so no installable firmware is produced.

Final verification:48 tests, no skips,34.771 seconds;29 model cases. Persistent build/ep5-completion-module/film.bin is31,578 bytes, spare1,174, SHA256e7ef2db733ff952926fde4158c4f6da27e6441378663cae89e87133dd65e0533. Its manifest source hashes and payload were checked against the current tree and final model report. Evidence:docs/completion-gate-verification.json; model log:generated/completion-gate-full-tests.log. Default disabled; no camera or update container output.
