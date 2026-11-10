/* Synthetic test caller only; no address in this file is a camera hook. */
#include "film.h"

struct request { uint32_t pixels, capacity, width, height, stride, lut, values; };
extern void ep5_probe_done(void);

static int progress(void *context, uint32_t done, uint32_t total)
{
    (void)total;
    return done < *(volatile const uint32_t *)context;
}

__attribute__((section(".text.probe")))
void ep5_probe(void)
{
    volatile const struct request *r = (const void *)0x11000000;
    volatile const uint32_t *control = (const void *)0x12000000;
    struct ep5_image image = {(uint8_t *)(uintptr_t)r->pixels, r->capacity, r->width, r->height, r->stride};
    int result = 0;
    if (control[3])
        result = ep5_image_from_desc(&image, (const void *)0x12000010, 32,
                                     r->pixels, image.data, image.capacity);
    if (!result)
        result = ep5_film_apply(&image, (const uint16_t *)(uintptr_t)r->lut, r->values,
                                 control[0], control[1], progress, (void *)0x12000008);
    *(volatile int32_t *)0x1100001c = result;
    ep5_probe_done();
}
