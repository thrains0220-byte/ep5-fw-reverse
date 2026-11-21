/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Single-threaded host driver with an explicit virtual SD root.
 * stdin/stdout carry one packed YUYV frame. No camera I/O. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "film_shot.h"

static uint16_t first[EP5_LUT_VALUES], second[EP5_LUT_VALUES], adjusted[EP5_LUT_VALUES];
static void noop(void *ctx) { (void)ctx; }
static void *card_open(void *ctx, const char *path)
{
    char target[4096];
    int n = snprintf(target, sizeof target, "%s/%s", (const char *)ctx, path);
    return n > 0 && (size_t)n < sizeof target ? fopen(target, "rb") : NULL;
}
static void *card_open_medium(void *ctx, uint32_t medium, const char *path)
{
    const struct ep5_look_io *bank = ctx;
    return medium == 1u ? bank->open(bank->ctx, path) : NULL;
}
static int32_t card_read(void *ctx, void *file, uint8_t *out, uint32_t count)
{
    (void)ctx;
    size_t n = fread(out, 1, count, file);
    return ferror(file) ? -1 : (int32_t)n;
}
static int card_close(void *ctx, void *file) { (void)ctx; return fclose(file); }

static int wheel_read(void *root, uint32_t mount, const char *path, uint8_t *record)
{
    if (mount != 1u) return -1;
    FILE *input = card_open(root, path);
    if (!input) return errno == ENOENT ? 0 : -1;
    size_t copied = fread(record, 1, EP5_WHEEL_FILE_BYTES, input);
    int valid = copied == EP5_WHEEL_FILE_BYTES && fgetc(input) == EOF && !ferror(input);
    return fclose(input) == 0 && valid ? 1 : -1;
}

/* This renderer opens an existing card as a read-only photo source. */
static int wheel_readonly(void *root, uint32_t mount, const char *path, const uint8_t *record)
{
    (void)root; (void)mount; (void)path; (void)record;
    return -1;
}

static unsigned number(const char *s, unsigned max)
{
    char *end;
    errno = 0;
    unsigned long n = strtoul(s, &end, 10);
    if (!*s || *s == '-' || *end || errno || n > max) {
        fprintf(stderr, "Invalid number: %s\n", s);
        exit(2);
    }
    return (unsigned)n;
}

static int select_look(struct ep5_camera_menu *ui, unsigned mode, unsigned variant, unsigned amount)
{
    struct ep5_lut_menu *menu = &ui->looks;
    for (unsigned i = 0; i < EP5_LUT_MENU_SLOTS; ++i) {
        const struct ep5_lut_menu_slot *s = menu->slots + menu->cursor;
        if (s->configured && s->picture_mode == mode && s->variant == variant) {
            /* Use exactly the dial increments supported by the menu. */
            for (unsigned j = 0; j < 17 && menu->amount_q8 != amount; ++j)
                ep5_camera_menu_event(ui, 1, menu->amount_q8 > amount ? 0x9008 : 0x900a);
            return menu->amount_q8 == amount && ep5_camera_menu_event(ui, 1, 0x900c) == 2 &&
                   ep5_camera_menu_event(ui, 1, 0x9014) == EP5_CAMERA_SHOW_GROUPS &&
                   ep5_camera_menu_event(ui, 1, 0x9014) == 3;
        }
        ep5_camera_menu_event(ui, 1, 0x9006);
    }
    return 0;
}

static int progress(void *ctx, uint32_t rows, uint32_t total)
{
    (void)total;
    return rows < *(const uint32_t *)ctx;
}

/* This process exclusively owns the buffer after reading stdin. stdout is
 * available to the JPEG caller only after a successful handoff. */
struct host_capture {
    uint32_t token;
    struct ep5_image image;
    int submitted;
};

static int host_claim(void *ctx, uint32_t token, struct ep5_image *out, unsigned *encoding)
{
    struct host_capture *frame = ctx;
    if (token != frame->token) return 0;
    *out = frame->image;
    *encoding = EP5_BT601_FULL_YUYV;
    return 1;
}

static int host_submit(void *ctx, uint32_t token, int result)
{
    struct host_capture *frame = ctx;
    if (token != frame->token || (result != EP5_PHOTO_STOCK && result != EP5_PHOTO_STYLED)) return 0;
    frame->submitted = 1;
    return 1;
}

static void host_discard(void *ctx, uint32_t token)
{
    struct host_capture *frame = ctx;
    if (token == frame->token) frame->token = 0;
}

int main(int argc, char **argv)
{
    if (argc != 13 && argc != 14) {
        fputs("width height mode variant amount_q8 grain|auto halation bloom seed stop_row bank card [wheel-file]\n", stderr);
        return 2;
    }
    unsigned width = number(argv[1], 8192), height = number(argv[2], 8192);
    unsigned mode = number(argv[3], 65535), variant = number(argv[4], 255), amount = number(argv[5], 256);
    int use_preset = !strcmp(argv[6], "auto");
    struct ep5_film_fx_settings manual_fx = {
        .grain = use_preset ? 0u : number(argv[6], 100),
        .halation = number(argv[7], 100), .bloom = number(argv[8], 100), .seed = number(argv[9], UINT32_MAX)};
    uint32_t stop = number(argv[10], UINT32_MAX);
    if (!width || (width & 1) || !height) return 2;
    struct ep5_wheel_edit edit;
    if (argc == 14) {
        uint8_t record[EP5_WHEEL_FILE_BYTES + 1];
        FILE *f = fopen(argv[13], "rb");
        if (!f) return 2;
        size_t n = fread(record, 1, sizeof record, f);
        int ok = !ferror(f) && ep5_wheel_decode(record, n, &edit);
        if (fclose(f) || !ok) return 2;
    }
    struct ep5_lut_preload loader;
    struct ep5_look_io root = {argv[12], card_open, card_read, card_close};
    struct ep5_camera_menu ui = {0};
    struct ep5_camera_choice confirmed;
    struct ep5_camera_wheel_store edits = {argv[12], wheel_read, wheel_readonly};
    unsigned bank = number(argv[11], EP5_LUT_BANK_COUNT);
    if (!bank || !ep5_camera_menu_init(&ui, &root, 1) || !ep5_camera_menu_attach_store(&ui, &edits)) return 2;
    for (unsigned i = 1; i < bank; ++i) ep5_camera_menu_event(&ui, 1, 0x9006);
    if (ep5_camera_menu_event(&ui, 1, 0x900c) != EP5_CAMERA_LOAD_GROUP) return 2;
    while (ep5_camera_menu_step(&ui, 1) == EP5_LUT_JOB_BUSY) { }
    struct ep5_look_io *index_io = &ui.browser.views[bank - 1];
    struct ep5_lut_preload_io io = {index_io, card_open_medium, card_read, card_close};
    struct ep5_lut_preload_sync sync = {NULL, noop, noop};
    if (!ep5_lut_preload_init(&loader, &io, &sync, first, second, sizeof first)) return 2;
    ep5_lut_preload_media(&loader, 1);
    if (ui.looks.state != EP5_LUT_MENU_READY || !select_look(&ui, mode, variant, amount) ||
        !ep5_camera_menu_capture(&ui, 1, &confirmed) || confirmed.bank != bank) {
        fputs("Could not confirm the requested SD look\n", stderr);
        return 2;
    }
    if (!ep5_lut_preload_select(&loader, 1, &confirmed.look)) return 2;
    int status;
    do { status = ep5_lut_preload_step(&loader); } while (status == EP5_LUT_JOB_BUSY);
    struct ep5_shot_recipe recipe;
    int preset = ep5_shot_prepare(&recipe, &confirmed, use_preset && status == EP5_LUT_JOB_APPLY ? index_io : NULL,
                                  1, manual_fx.seed);
    if (!use_preset) recipe.fx = manual_fx;
    if (!ep5_camera_menu_choice_current(&ui, 1, &confirmed)) return 2;
    struct ep5_camera_choice shutter;
    if (!ep5_camera_menu_capture(&ui, 1, &shutter)) return 2;
    if (argc == 14 && edit.picture_mode == shutter.look.picture_mode && edit.variant == shutter.look.variant &&
        edit.number == shutter.look.number && edit.look_crc == shutter.look.look_crc) {
        shutter.wheel = edit.values;
        shutter.has_wheel = 1;
    }

    struct ep5_capture_sequence sequence = {0};
    uint32_t token = ep5_capture_begin(&sequence, &loader, width, height, &recipe, &shutter);
    if (!token) return 2;
    size_t bytes = (size_t)width * height * 2u;
    uint8_t *pixels = malloc(bytes);
    size_t scratch = ep5_film_fx_scratch_bytes(width, &recipe.fx);
    void *ring = scratch ? malloc(scratch) : NULL;
    int exit_code = 2;
    if (!pixels || fread(pixels, 1, bytes, stdin) != bytes ||
        fgetc(stdin) != EOF || ferror(stdin)) {
        ep5_capture_cancel_pending(&sequence, token);
        goto finish;
    }
    struct host_capture frame = {token, {pixels, bytes, width, height, width * 2u}, 0};
    const struct ep5_capture_backend backend = {&frame, host_claim, host_submit, host_discard};
    struct ep5_photo_workspace work = {adjusted, EP5_LUT_VALUES, ring, scratch};
    int result = ep5_capture_ready(&sequence, token, &backend, &work, progress, &stop);
    fprintf(stderr, "{\"result\":%d,\"preload\":%d,\"released\":%s,\"look_crc\":%u,\"preset\":%d,\"wheel\":%s}\n",
            result, status, loader.pinned == NULL ? "true" : "false", (unsigned)shutter.look.look_crc, preset,
            shutter.has_wheel ? "true" : "false");
    if (frame.submitted)
        exit_code = fwrite(pixels, 1, bytes, stdout) == bytes && fflush(stdout) == 0 ? 0 : 2;
    else exit_code = 3;
finish:
    free(ring);
    free(pixels);
    return exit_code;
}
