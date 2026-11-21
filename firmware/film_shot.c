/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "film_shot.h"
#include "film_fx_preset.h"
#include "object_bytes.h"

int ep5_shot_prepare(struct ep5_shot_recipe *recipe, const struct ep5_camera_choice *choice,
                     const struct ep5_look_io *io, uint32_t medium, uint32_t grain_seed)
{
    if (!recipe) return -1;
    recipe->medium = 0;
    if (!choice || !choice->mount || !choice->revision || !medium ||
        !choice->bank || choice->bank > EP5_LUT_BANK_COUNT) return -1;
    recipe->look = choice->look;
    recipe->mount = choice->mount;
    recipe->bank = choice->bank;
    recipe->revision = choice->revision;
    recipe->medium = medium;
    if (!io) return ep5_film_fx_preset(NULL, 0, &choice->look, grain_seed, &recipe->fx);
    return ep5_film_fx_preset_load(io, &choice->look, grain_seed, &recipe->fx);
}

int ep5_shot_develop(struct ep5_lut_preload *loader, uint32_t shot,
                     const struct ep5_shot_recipe *recipe, const struct ep5_camera_choice *current,
                     const struct ep5_image *image, unsigned encoding,
                     const struct ep5_photo_workspace *work,
                     int (*progress)(void *, uint32_t, uint32_t), void *context)
{
    if (!loader || !shot || !ep5_image_valid(image) || encoding != EP5_BT601_FULL_YUYV)
        return EP5_PHOTO_INVALID;
    if (!recipe || !current || !recipe->medium) return EP5_PHOTO_STOCK;
    const struct ep5_lut_menu_capture *a = &recipe->look, *b = &current->look;
    if (current->mount != recipe->mount || current->bank != recipe->bank || current->revision != recipe->revision ||
        a->picture_mode != b->picture_mode || a->variant != b->variant || a->number != b->number ||
        a->look_crc != b->look_crc || a->amount_q8 != b->amount_q8) return EP5_PHOTO_STOCK;
    struct ep5_photo_style style;
    style.medium = recipe->medium;
    style.choice = *b;
    ep5_copy_bytes(&style.fx, &recipe->fx, sizeof style.fx);
    style.wheel = NULL;
    style.wheel_medium = 0;
    struct ep5_wheel_edit wheel;
    if (current->has_wheel) {
        wheel.picture_mode = b->picture_mode;
        wheel.variant = b->variant;
        wheel.number = b->number;
        wheel.look_crc = b->look_crc;
        for (unsigned axis = 0; axis < 3; ++axis)
            for (unsigned i = 0; i < EP5_WHEEL_SECTORS; ++i)
                wheel.values.axis[axis][i] = current->wheel.axis[axis][i];
        style.wheel = &wheel;
        style.wheel_medium = recipe->medium;
    }
    return ep5_photo_render(loader, shot, &style, image, encoding, work, progress, context);
}
