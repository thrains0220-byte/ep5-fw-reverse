#include "lut_bank.h"
#include <string.h>

/* Returns a result to the Python fixture which supplies the real ZIP backend. */
int bank_browse_real_card(const struct ep5_look_io *card)
{
    struct ep5_lut_bank_browser browser = {0};
    struct ep5_lut_menu menu;
    struct ep5_lut_menu_capture capture;
    ep5_lut_menu_init(&menu);
    if (!ep5_lut_bank_browser_init(&browser, card)) return 0;
    unsigned seq[] = {1, 2, 3, 1};
    char *names[] = {"Velvia", "Pr400H", "Atrphy", "Velvia"};
    for (unsigned i = 0; i < 4; ++i) {
        if (!ep5_lut_bank_select(&browser, &menu, seq[i]) || ep5_lut_menu_capture(&menu, &capture)) return 0;
        if (ep5_lut_bank_select(&browser, &menu, ep5_lut_bank_next(seq[i], 1))) return 0;
        int result;
        do { result = ep5_lut_bank_step(&browser, &menu); } while (result == EP5_LUT_JOB_BUSY);
        if (result != EP5_LUT_JOB_INDEX_READY || menu.state != EP5_LUT_MENU_READY) return 0;
        unsigned count = 0;
        for (unsigned j=0; j<EP5_LUT_MENU_SLOTS; ++j) count += menu.slots[j].configured;
        if (count != (seq[i] == 3 ? 1u : 14u)) return 0;
        for (unsigned j=0; j<=strlen(names[i]); ++j)
            if (menu.slots[0].label[j] != (unsigned char)names[i][j]) return 0;
        if (ep5_lut_menu_capture(&menu,&capture) || ep5_lut_menu_event(&menu,EP5_LUT_MENU_OK)!=2 ||
            !ep5_lut_menu_capture(&menu,&capture) || !capture.look_crc) return 0;
    }
    /* Close a half-read index. The worker must release the old handle and its
     * stale completion may neither reopen the menu nor restore the selection. */
    if (!ep5_lut_bank_select(&browser, &menu, 2) || ep5_lut_bank_step(&browser, &menu) != EP5_LUT_JOB_BUSY)
        return 0;
    if (ep5_lut_menu_event(&menu, EP5_LUT_MENU_BACK) != 3) return 0;
    int result;
    do { result=ep5_lut_bank_step(&browser,&menu); } while(result==EP5_LUT_JOB_BUSY);
    return result == EP5_LUT_JOB_CANCELLED && menu.state == EP5_LUT_MENU_HIDDEN &&
           !ep5_lut_menu_capture(&menu,&capture);
}
