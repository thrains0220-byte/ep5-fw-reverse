#include "lut_bank.h"
#include "look_path.h"

int ep5_lut_bank_path(char out[EP5_LUT_BANK_PATH_CAP], unsigned number, const char *path)
{
    const char *prefix = EP5_LOOK_ROOT;
    const char *p = ep5_look_after_root(path);
    if (!out || !p || number < 1 || number > EP5_LUT_BANK_COUNT || !ep5_look_valid_leaf(p))
        return 0;
    unsigned length = 0;
    for (; prefix[length]; ++length) out[length] = prefix[length];
    if (number != 1) {
        out[length++] = 'B'; out[length++] = '0';
        out[length++] = (char)('0' + number); out[length++] = '/';
    }
    do { out[length++] = *p; } while (*p++);
    return 1;
}

static void *bank_open(void *ctx, const char *logical)
{
    struct ep5_lut_bank *bank = ctx;
    char physical[EP5_LUT_BANK_PATH_CAP];
    if (!ep5_lut_bank_path(physical, bank->number, logical)) return 0;
    return bank->parent.open(bank->parent.ctx, physical);
}
static int32_t bank_read(void *ctx, void *file, uint8_t *dst, uint32_t count)
{
    struct ep5_lut_bank *bank = ctx;
    return bank->parent.read(bank->parent.ctx, file, dst, count);
}
static int bank_close(void *ctx, void *file)
{
    struct ep5_lut_bank *bank = ctx;
    return bank->parent.close(bank->parent.ctx, file);
}

int ep5_lut_bank_bind(struct ep5_lut_bank *bank, struct ep5_look_io *view,
                      const struct ep5_look_io *parent, unsigned number)
{
    if (!bank || !view || !parent || !parent->open || !parent->read || !parent->close ||
        !number || number > EP5_LUT_BANK_COUNT || view == parent || parent->open == bank_open) return 0;
    bank->number = (uint8_t)number;
    bank->parent = *parent;
    view->ctx = bank;
    view->open = bank_open;
    view->read = bank_read;
    view->close = bank_close;
    return 1;
}

unsigned ep5_lut_bank_next(unsigned number, int direction)
{
    if (!number || number > EP5_LUT_BANK_COUNT) return 0;
    if (direction > 0) return number == EP5_LUT_BANK_COUNT ? 1 : number + 1;
    if (direction < 0) return number == 1 ? EP5_LUT_BANK_COUNT : number - 1;
    return number;
}

int ep5_lut_bank_browser_init(struct ep5_lut_bank_browser *browser, const struct ep5_look_io *parent)
{
    if (!browser) return 0;
    for (unsigned i = 0; i < EP5_LUT_BANK_COUNT; ++i)
        if (!ep5_lut_bank_bind(&browser->banks[i], &browser->views[i], parent, i + 1)) return 0;
    ep5_lut_job_init(&browser->job);
    browser->selected = 0;
    return 1;
}

int ep5_lut_bank_select(struct ep5_lut_bank_browser *browser, struct ep5_lut_menu *menu,
                        unsigned number)
{
    if (!browser || !menu || !number || number > EP5_LUT_BANK_COUNT) return 0;
    uint16_t generation = (uint16_t)(menu->generation + 1u);
    if (!generation) generation = 1;
    /* A busy reader keeps its bank binding. Retry after its current job is
     * finished or cancelled and closed by the file task. */
    if (!ep5_lut_job_request_index(&browser->job, &browser->views[number - 1], browser->staging,
                                   generation)) return 0;
    if (browser->selected != number) {
        menu->applied = 0;
        menu->previous = 0;
        menu->cursor = 0;
    }
    browser->selected = number;
    return ep5_lut_menu_begin_load(menu, generation);
}

int ep5_lut_bank_step(struct ep5_lut_bank_browser *browser, struct ep5_lut_menu *menu)
{
    if (!browser || !menu || !browser->selected) return EP5_LUT_JOB_ERROR;
    int status = ep5_lut_job_step(&browser->job, menu->generation);
    if (status == EP5_LUT_JOB_INDEX_READY || status == EP5_LUT_JOB_ERROR)
        (void)ep5_lut_menu_finish_index(&browser->job, menu);
    return status;
}
