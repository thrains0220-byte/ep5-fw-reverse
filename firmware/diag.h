#ifndef EP5_DIAG_H
#define EP5_DIAG_H
#include <stddef.h>
#include <stdint.h>

/* D diagnostic branch: observe the real JPEG buffer contract (S4) and resource
 * lifetime (S5) WITHOUT writing pixels or neutralizing the ART packet. Stock
 * imaging runs untouched. Observations are logged to SD via the stock write
 * service at a safe point after the shot. See docs/FILE_SERVICE_MAP.md.
 *
 * This module is built only with -DEP5_DIAG and is a hardware-diagnostic
 * candidate, never a functional LUT candidate. */

#define EP5_DIAG_MAGIC 0x47414944u /* "DIAG" */
#define EP5_DIAG_RECORD_BYTES 128u
#define EP5_DIAG_MAX_RECORDS 8u

/* One observation record, little endian, fixed layout. */
struct ep5_diag_record {
    uint32_t magic;          /* EP5_DIAG_MAGIC */
    uint32_t seq;            /* shot sequence */
    uint32_t jpeg_request;   /* request pointer (CPU addr) */
    uint32_t buffer_addr;    /* request+0 : YC buffer base */
    uint16_t width;          /* request+4 */
    uint16_t height;         /* request+6 */
    uint16_t store_w;        /* request+8 */
    uint16_t store_h;        /* request+10 */
    uint32_t global_addr;    /* 0x605f455c image global */
    uint32_t context;        /* completion context */
    uint8_t  fmt_byte36;     /* request[36] format/flags */
    uint8_t  sample[16];     /* first 16 bytes of buffer (Y0 Cb Y1 Cr ...) */
    uint32_t pool_ptr;       /* look_state pool block if any */
    uint32_t flags;          /* bit0 buffer readable, bit1 sample taken */
    uint32_t reserved[17];   /* pad to exactly 128 bytes */
};

/* Zero the observation state once per boot. The cave loads from 0xFF-filled
 * flash into RAM; .bss is NOT zero-initialized by any startup code. */
void ep5_diag_init(void);

/* Capture one observation from the JPEG request. Read-only on the buffer.
 * Returns 1 if a record was stored, 0 if rejected. Never writes pixels. */
int ep5_diag_observe(const uint8_t *request, const void *context, uint32_t global_addr);

/* Flush accumulated records to SD (EP5LUT/DIAG.LOG) via stock write service.
 * Called at a safe point (release), not in the shutter path. Returns bytes
 * written or negative on error. */
int32_t ep5_diag_flush(void);

#endif
