# Flashable E-P5 delivery target and native image handoff

> Continue inline under the user's existing execution authorization. Acceptance is a camera firmware modification, not a desktop tool or SDK. No additional design approval round.

**Goal:** an E-P5-specific update image that enables full-resolution in-camera film rendering after installation, preserving ORF; include supported baseline, installation/disable/recovery instructions and output evidence.

**Architecture:** use native Olympus development and JPEG encoding where possible, insert the tested colour engine only on a proved CPU-accessible image path. Film profiles are separate from body-specific addresses. External projects supply mechanisms, not transferable Canon/other-Olympus firmware bytes.

## This continuation

- [x] Re-read Ritual official workflow and inspect Soup Engine, M-Film, E-M10 and E-P7 sources at fixed revisions.
- [x] Add a failing test for E-P5 original `rec_art_make_prim` → `REC MISC YC2JPG` handoff, including full-size geometry and original call/return frames.
- [x] Execute that original route with read-only synthetic ART globals/context; model logging and codec only, capture the native request without substituting its builder.
- [x] Record exact 40-byte input offsets and where evidence ends; this ART route is not yet the normal still route.
- [x] Write the source comparison and concrete flashable-product acceptance criteria; run suite and independent review.
- [x] Commit and sync feature branch work/ep5-film.

## Next native integration work

1. Trace the producer of ART buffer globals `0x605f455c`/`0x605f4560`, format/range, completion and release. Test whether a neutral full-size route can be selected without retaining a stock ART effect or reducing resolution.
2. Compare native ISP curve/preset modification against software 3D LUT injection. Prefer ISP for a look it can represent, software for full RGB cross-channel LUTs; do not claim the ISP implements arbitrary .cube transforms.
3. Establish code/LUT storage, frame-safe veneers, task/cache contracts and an explicit bypass. Build firmware from exact stock with original-byte guards and container verification; current unidentified camera image must not be treated as the reference.
4. Add real film profiles with explicit input colour space and provenance, selectable in camera, plus optional SD profile import. First firmware should have a built-in look so an empty card does not make the feature disappear.
5. Test the actual update image on the camera, full-resolution ORF+JPEG, effect selection/disable, repeated shots and restoration. Until this passes, mark any generated image experimental and do not describe an emulator binary as flashable firmware.

## Rulings

Ruling: reference multiple sources directly — Ritual is confirmed to offer in-camera film output, but no source entry was established on its inspected public pages. Soup Engine/M-Film provide readable camera/workflow code; E-M10 provides closer MN103/ISP/loader contracts. E-P7's addresses and newer ISP structures are architectural leads only.

Ruling: examine the ART→JPEG handoff now instead of adding another generic effect — a verified original handoff reduces a body-specific integration unknown; it does not yet qualify an insertion point or resolve code residency.

Result: native full-size geometry handoff 105 instructions, small geometry/options branch 112; both preserve call/return frames, propagate modeled codec result and pass readonly-input/write-boundary checks. Full suite 40 tests passed with no skips in 29.295 seconds. Independent reviewer ran both image tests in an isolated copy, confirmed native disassembly and reported no actionable findings. Source comparison and final acceptance are in docs/FLASHABLE_PRODUCT.md; no firmware package, runtime hook or image-production proof was created.
