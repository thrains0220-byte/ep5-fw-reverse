# Asynchronous LUT loading boundary

`firmware/lut_job.c` is a host-tested worker state machine for the existing `EP5IDX02` / `EP5LUT01` protocol. It is deliberately separate from the camera hooks: it does not contain an E-P5 address, task identifier, or UI call.

A UI or controller submits one request with `(picture_mode, variant, generation)`. The worker then advances in small steps:

1. Open and validate `EP5LUT/INDEX.EP5`.
2. Read one 28-byte row per step, validating slot uniqueness, amount, number, label and CRC.
3. Close the index and either select stock (missing or zero-strength slot) or open the selected LUT.
4. Read at most `EP5_LUT_JOB_CHUNK` (512) wire bytes per step into the staging table, validate the LUT header, length and CRC, then close it.
5. Convert little-endian wire words in bounded chunks and atomically swap the completed staging table into the caller-owned cache.

The worker copies the IO vtable and all request scalars. It never keeps a pointer to a menu row or SD label. A generation change cancels the request; cancellation closes an open handle on a following step and never publishes the staging table. Any malformed file, short read, close error, or unexpected trailing byte produces `EP5_LUT_JOB_ERROR`, while an unsupported or zero-strength slot produces `EP5_LUT_JOB_STOCK`.

This prevents the key callback and display callback from synchronously reading a roughly 30 KB LUT. It does not prove that the stock E-P5 FILEFGND wrapper is safe for this worker: the supplied `ep5_look_io` backend still has to be adapted to the real file task, queue, cancellation and cache/DMA ownership. Until those contracts are measured on an E-P5, this module remains an offline integration boundary and must not be linked into a functional update image.

The C fixture `tests/test_lut_job.c` exercises a complete apply, generation cancellation, missing LUT, unsupported slot, damaged index/table CRC, short read, trailing bytes, close failure and the 512-byte read bound. Failed loads leave the active table untouched. The worker also compiles freestanding with the bundled MN103 compiler without external symbols. These are host/compiler checks, not camera-task validation.
