/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef EP5_OBJECT_BYTES_H
#define EP5_OBJECT_BYTES_H
#include <stddef.h>

/* MN103 can lower aggregate assignment/initialization to libc calls, even
 * in a freestanding build. Copy the complete object representation instead. */
static inline void ep5_copy_bytes(void *dst, const void *src, size_t size)
{
    unsigned char *out = dst;
    const unsigned char *in = src;
    for (size_t i = 0; i < size; ++i)
        out[i] = in[i];
}

static inline void ep5_zero_bytes(void *dst, size_t size)
{
    unsigned char *out = dst;
    for (size_t i = 0; i < size; ++i)
        out[i] = 0;
}
#endif
