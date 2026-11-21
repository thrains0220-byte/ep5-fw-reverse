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

static int recipe_matches(const struct ep5_shot_recipe *recipe, const struct ep5_camera_choice *current)
{
    if (!recipe || !current || !recipe->medium) return 0;
    const struct ep5_lut_menu_capture *a = &recipe->look, *b = &current->look;
    return current->mount == recipe->mount && current->bank == recipe->bank && current->revision == recipe->revision &&
        a->picture_mode == b->picture_mode && a->variant == b->variant && a->number == b->number &&
        a->look_crc == b->look_crc && a->amount_q8 == b->amount_q8;
}

static void make_style(struct ep5_photo_style *style, struct ep5_wheel_edit *wheel,
                       const struct ep5_shot_recipe *recipe, const struct ep5_camera_choice *current)
{
    const struct ep5_lut_menu_capture *b = &current->look;
    style->medium = recipe->medium;
    style->choice = *b;
    ep5_copy_bytes(&style->fx, &recipe->fx, sizeof style->fx);
    style->wheel = NULL;
    style->wheel_medium = recipe->medium;
    if (current->has_wheel) {
        wheel->picture_mode = b->picture_mode;
        wheel->variant = b->variant;
        wheel->number = b->number;
        wheel->look_crc = b->look_crc;
        ep5_copy_bytes(&wheel->values, &current->wheel, sizeof wheel->values);
        style->wheel = wheel;
    }
}

int ep5_shot_develop(struct ep5_lut_preload *loader, uint32_t shot,
                     const struct ep5_shot_recipe *recipe, const struct ep5_camera_choice *current,
                     const struct ep5_image *image, unsigned encoding,
                     const struct ep5_photo_workspace *work,
                     int (*progress)(void *, uint32_t, uint32_t), void *context)
{
    struct ep5_photo_style style;
    struct ep5_wheel_edit wheel;
    if (!loader || !shot || !ep5_image_valid(image) || encoding != EP5_BT601_FULL_YUYV)
        return EP5_PHOTO_INVALID;
    if (!recipe_matches(recipe, current)) return EP5_PHOTO_STOCK;
    make_style(&style, &wheel, recipe, current);
    return ep5_photo_render(loader, shot, &style, image, encoding, work, progress, context);
}

enum capture_phase { CAPTURE_IDLE, CAPTURE_WAITING, CAPTURE_PROCESSING };

uint32_t ep5_capture_begin(struct ep5_capture_sequence *sequence, struct ep5_lut_preload *loader,
                           uint32_t width, uint32_t height,
                           const struct ep5_shot_recipe *recipe, const struct ep5_camera_choice *choice)
{
    if (!sequence || sequence->phase != CAPTURE_IDLE || sequence->last == UINT32_MAX ||
        !width || (width & 1u) || !height) return 0;
    sequence->width = width;
    sequence->height = height;
    ++sequence->last;
    if (loader && recipe_matches(recipe, choice) && choice->look.amount_q8 &&
        ep5_lut_preload_acquire(loader, recipe->medium, sequence->last, &choice->look, &sequence->look)) {
        sequence->owner = loader;
        make_style(&sequence->style, &sequence->wheel, recipe, choice);
    }
    sequence->phase = CAPTURE_WAITING;
    return sequence->last;
}

static int awaiting(const struct ep5_capture_sequence *sequence, uint32_t token)
{
    return sequence && token && sequence->phase == CAPTURE_WAITING && sequence->last == token;
}

static void release_table(struct ep5_capture_sequence *sequence)
{
    if (sequence->owner) {
        /* This sequence owns the sole pin until its matching completion or cancellation. */
        ep5_lut_preload_release(sequence->owner, sequence->last);
        sequence->owner = NULL;
    }
}

int ep5_capture_cancel_pending(struct ep5_capture_sequence *sequence, uint32_t token)
{
    if (!awaiting(sequence, token)) return 0;
    release_table(sequence);
    sequence->phase = CAPTURE_IDLE;
    return 1;
}

int ep5_capture_ready(struct ep5_capture_sequence *sequence, uint32_t token,
                      const struct ep5_capture_backend *backend,
                      const struct ep5_photo_workspace *work,
                      int (*progress)(void *, uint32_t, uint32_t), void *context)
{
    if (!awaiting(sequence, token)) return EP5_CAPTURE_IGNORED;
    /* Consume the notification before calling any platform function. */
    sequence->phase = CAPTURE_PROCESSING;
    int result = EP5_CAPTURE_BYPASS;
    struct ep5_image frame = {0};
    unsigned encoding = 0;
    if (backend && backend->claim && backend->submit && backend->discard &&
        backend->claim(backend->context, token, &frame, &encoding) == 1) {
        result = EP5_PHOTO_INVALID;
        if (frame.width == sequence->width && frame.height == sequence->height && ep5_image_valid(&frame)) {
            result = EP5_PHOTO_STOCK;
            if (sequence->owner && encoding == EP5_BT601_FULL_YUYV)
                result = ep5_photo_render_pinned(&sequence->look, &sequence->style, &frame, encoding,
                                                 work, progress, context);
        }
        if (result == EP5_PHOTO_STYLED || result == EP5_PHOTO_STOCK) {
            if (backend->submit(backend->context, token, result) != 1) result = EP5_PHOTO_DISCARD;
        }
        if (result < 0) backend->discard(backend->context, token);
    }
    release_table(sequence);
    sequence->phase = CAPTURE_IDLE;
    return result;
}
