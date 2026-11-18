# Asynchronous LUT loading boundary

`firmware/lut_job.c` is a host-tested worker state machine for the existing `EP5IDX02` / `EP5LUT01` protocol. It is deliberately separate from the camera hooks: it does not contain an E-P5 address, task identifier, or UI call.

A UI or controller submits one request with `(picture_mode, variant, generation)`. The worker then advances in small steps:

1. Open and validate `EP5LUT/INDEX.EP5`.
2. Read one 28-byte row per step, validating slot uniqueness, amount, number, label and CRC.
3. Close the index and either select stock (missing or zero-strength slot) or open the selected LUT.
4. Read at most `EP5_LUT_JOB_CHUNK` (512) wire bytes per step into the staging table, validate the LUT header, length and CRC, then close it.
5. Convert little-endian wire words in bounded chunks and swap the two pointers in the worker-owned cache. Cross-task publication is a separate operation under the coordinator lock.

The worker copies the IO vtable and all request scalars. It never keeps a pointer to a menu row or SD label. A generation change cancels the request; cancellation closes an open handle on a following step and never publishes the staging table. Any malformed file, short read, close error, or unexpected trailing byte produces `EP5_LUT_JOB_ERROR`, while an unsupported or zero-strength slot produces `EP5_LUT_JOB_STOCK`.

`firmware/lut_preload.c` coordinates the menu, the worker and the shot. It copies the confirmed selection and binds the index row to the look number and table CRC. The amount comes from the user's choice. Changing only the amount of a published look needs no I/O. Selecting another look, removing the card or refreshing its contents invalidates publication for new shots. The worker closes its old handle before starting a replacement request. A shot can acquire only a completed table that matches its confirmed choice and mount ID. It retains that table until all readers release it, even if another table finishes loading. After a swap, a worker that needs the pinned buffer returns `EP5_LUT_PRELOAD_WAIT_SHOT` so its scheduler can suspend it until release or invalidation.

The camera adapter owns the synchronization and notification contracts. Give every mount, refresh and shot a fresh nonzero ID and deliver unmount before allowing another shot to acquire a table. The file backend must validate the mount ID and open on that mount as one operation. Read and close continue to refer to that handle after any media change. Run `step` from one file worker and schedule it after selection, cancellation and shot release as needed. The lock protects metadata and must also establish visibility of the completed table. It is released before I/O. A bounded read byte count leaves the latency of the backend call itself unconstrained. Physical card removal, cache visibility and the GUI and file task lifetimes still need a camera adapter and hardware validation. The existing mode 3 experiment uses synchronous loading in `ep5_art_entry.c`.

The C fixture `tests/test_lut_job.c` exercises complete publication, cancel during a read, stale mount and selection, mount change before open, table ownership across two swaps, amount changes without a reload, and stock fallback. Corrupt files, short reads, extra bytes and close errors leave the previous active table intact. Build it with the host compiler from the repository root. Both modules also compile freestanding for MN103.

```sh
cc -std=c99 -O2 -Wall -Wextra -Werror -Ifirmware \
  tests/test_lut_job.c firmware/lut_job.c firmware/lut_preload.c \
  firmware/look_store.c -o /tmp/ep5-lut-job-test
/tmp/ep5-lut-job-test
```

The [FILEFGND map](FILE_SERVICE_MAP.md) records the stock loop and queue probes. Reproduce them with `python3 tools/audit_lut_runtime.py --execute` on a host with the decoded stock MAIN and the pinned CPU emulator checkout.

## Preloaded LUT at capture

`validate_look_runtime(image, model_preload=True)` links the existing preload worker into the MN103 ART/JPEG probe. The fixture supplies isolated RAM, a menu snapshot, mount events and worker ticks. The actual FILEFGND loop, local queue receive, ART send, wait, JPEG and release fragments, and the target LUT code run in the CPU model. `EP5_MODEL_PRELOAD` is selected by this test only.

The model sets the receive timeout to zero at the stock file loop's receive call. A stock read request runs through receive, dispatch and reply with its original cookie before the worker can advance. Only a poll result of `-2` (empty) permits a worker step. A queue error (`-1`) leaves the worker pending. The removal test invalidates the mounted look while its index handle is open, serves a pending stock request, then closes the old handle once on an empty poll. The model supplies the queue lock, scheduler, file backend and reply transport.

The send hook acquires the confirmed table and intensity without reading files or taking an ART pool allocation. If the table is unavailable, the entire stock send packet is preserved. A load that completes after the send cannot affect that exposure. A shot that acquired a table keeps it across a modeled unmount until the release hook. The probe exercises release after JPEG and after a canceled shot, including the check that no file is opened, read or closed by the capture stages. Each worker tick performs at most one file operation and reads at most 512 bytes.

Run `python3 -m unittest discover -s tests -p test_cave_entry.py -v` to cover nine preload cases and the previous ART paths. The image fixture is 4×20 YUYV and uses bytes generated by the existing desktop LUT packer. The probe checks pixel output against the host kernel along with guard bytes, stock argument frames, and ownership. Physical SD invalidation, native worker scheduling and locking, real GUI interaction, image buffer mapping, and full-size JPEG/ORF output require further validation. In particular, an error after the ART request has already been neutralized can still leave a neutral image. Only paths that preserve the original send packet qualify as stock fallback in this probe.

The 17³ trilinear kernel now derives its cell and fraction directly from the 16-bit input and uses one variable multiply and an exact integer correction for each blend. Compared with `76c4d60`, `tools/check_mn103_lut.py --film` counts 59,092 instructions for the warm-negative fixture, down from 69,059 (14.4%). The identity, full strength, and half strength outputs retain their original hashes. A host comparison of both revisions also matched across 65,536 coordinate triples from a seeded nonlinear table and all 31,850,496 bytes of a 4608×3456 YUYV fixture. This comparison tests arithmetic and buffer extent. Camera memory/cache behavior and full-frame wall time still require measurement.
