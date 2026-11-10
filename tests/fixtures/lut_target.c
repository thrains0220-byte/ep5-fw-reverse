/* Test-only GCC caller; these synthetic addresses are not camera hook locations. */
#include "lut.h"

struct request {
    uint32_t pixels, capacity, width, height, stride, lut, values;
};

extern void ep5_probe_done(void);

__attribute__((section(".text.probe")))
void ep5_probe(void)
{
    volatile const struct request *r = (const void *)0x11000000;
    int result = ep5_lut_rgb8((uint8_t *)(uintptr_t)r->pixels, r->capacity,
                             r->width, r->height, r->stride,
                             (const uint16_t *)(uintptr_t)r->lut, r->values);
    *(volatile int32_t *)0x1100001c = result;
    ep5_probe_done();
}
