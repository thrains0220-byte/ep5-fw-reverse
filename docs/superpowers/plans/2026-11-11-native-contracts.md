# E-P5 native allocation and neutral route implementation plan

> Execute inline using executing-plans and test-driven-development under the existing implementation/push authorization. Spec: docs/FLASHABLE_PRODUCT.md. No new design questions.

**Goal:** replace guessed ART producer/geometry and startup assumptions with reproducible execution of stock instructions, then identify the smallest neutral full-resolution firmware insertion route.

**Architecture:** reuse the pinned CPU engine and exact decoded main hash. A bounded probe runs stock startup argument construction, ART common initialization/allocation, and native filter-list construction. Only explicit logging, allocator and hardware-dependent boundaries are modeled; no host computation substitutes for geometry or filter selection.

**Scope:** create tools/ep5_contract_probe.c, tools/native_contracts.py, tests/test_native_contracts.py; update firmware integration evidence/docs/README. Existing colour module stays disabled until physical pixel/cache/task contracts are established. No new dependency or vendor payload redistribution.

## Tasks

- [x] Write failing tests for original boot read bounds, ART allocator size/output slot/failure, computed geometry and neutral versus stock ART filter function lists. Reject modified baseline.
- [x] Implement a bounded runner with native CALL/RET frames and write restrictions, expose a repeatable report through the existing build_probe helper. Run the tests and inspect actual native results, recording deviations below.
- [x] Trace the resulting minimal neutral integration route and document exact addresses and unresolved semantics. Qualify every claim by the service boundaries actually executed.
- [x] Run the complete suite, obtain a fresh review and address meaningful findings.
- [x] Commit and sync work/ep5-film.

## Review focus

- A request to read flash is not proof of successful physical loading or later residency.
- An allocator model supplies an address, never claims actual memory ownership or valid pixels.
- Table-derived/cropped geometry must not silently become duplicated full dimensions.
- A neutral filter list must retain RAW-to-YC conversion and actually omit effect functions.
- Native prologues and caller frames must match; writes outside mapped stack/packet/task records fail.

## Decisions and evidence

Ruling: execute original producer-side routines before expanding the firmware adapter — the existing 40-byte JPEG request test supplied its globals synthetically and cannot prove where those values originate. Cost if wrong: this probe would narrow the wrong capture branch; ordinary shooting entry still needs tracing.

Fixture correction during RED→GREEN: packet+2 selects the size mode and packet+96 selects the aspect table row; the initial fixture inverted those meanings and correctly produced 640×480. Use original mode3/aspect1 to obtain native 4608×3456; aspect2 computes the 3:2 geometry including 192-row offset, without prefilled dimensions. Correct cached alias conversion is `(address & 0x3fffffff) | 0x40000000`. Native initializer pointer resides at task+4, not the task header; added an assertion after observing this reporting error.

Scope refinement: successful allocation/initialization is followed by a separate native ART→JPEG request invocation in the probe, with the newly generated globals unchanged. This proves propagation, not intervening ISP execution or real-world failure scheduling. The input context and last allocator/JPEG services remain synthetic. No retained-geometry test is claimed; the existing-buffer case reuses its address while computing dimensions.

Initial focused four tests passed; initial whole suite:47 passed, no skips,35.147 seconds. Fresh reviewer independently passed4/4 in a temporary build and checked original disassembly.

Final review fixes: the comparator was mislabeled rough-monochrome; original literal references show +6=73 is pinhole. Corrected code/report/test/documentation to pinhole, preserving the identical RAW→YC converter comparison. Added assertions for cropped full allocation, allocation call/error sink, native results and initializer; four report mutations are rejected by these assertions. Changing the comparison key first produced the expected failing test, then the renamed implementation passed.

Final review fixes: parenthesized checked integer offsets before adding to host pointers, in the new mapper and the four existing related CPU harnesses (including cave patch memcpy/memcmp). This corrects C pointer-arithmetic undefined behavior; no deterministic runtime failure is claimed. Existing bounded-memory/native/target regression cases were all rerun. Earlier committed evidence JSON files are historical snapshots of their then-current harness sources; the new report fingerprints all five current harnesses.

Final review: regraded standalone success despite jpeg_frame_preserved=false from Minor to Important because the CLI is used as evidence outside unittest. Fault injection changing only the codec return marker reproduced exit0/false preservation; the CLI now returns1. Test test_cli_fails_when_codec_return_contract_is_corrupted RED→GREEN. No deferred minor findings.

Reviewer declined physical loading/residency, actual allocator/ISP/pixel/encoding judgement because those stop/model boundaries are explicit. These remain unverified integration requirements, not successful firmware features; enabling the module without them could corrupt output or destabilize the camera.

Final whole suite:48 passed, zero skips,34.841 seconds, generated/native-contracts-full-tests.log. Seven original-instruction cases plus the corrupted-codec fault-injection case. Current evidence:docs/native-contracts-verification.json. No flashable firmware, camera access, complete task lifecycle or pixel encoding qualification was added.
