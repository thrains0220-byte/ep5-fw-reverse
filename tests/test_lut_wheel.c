#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lut_wheel_view.h"

/* This host test also acts as a narrow stdout bridge for the Python reference
 * test. The optional mode reads 36 signed sliders and emits one RGB16LE table. */
static uint16_t table[EP5_LUT_VALUES], base[EP5_LUT_VALUES];

static void check_editor(void)
{
    struct ep5_lut_menu menu;
    struct ep5_lut_menu_slot slots[EP5_LUT_MENU_SLOTS] = {0};
    struct ep5_wheel_editor editor = {0};
    struct ep5_wheel_edit saved = {0}, loaded = {0};
    struct ep5_wheel_page page;
    uint32_t mount = 82;
    slots[3].number = 7;
    slots[3].picture_mode = 103;
    slots[3].variant = slots[3].configured = 1;
    slots[3].look_crc = 0x12345678;
    slots[3].label[0] = 'G';
    slots[3].amount_q8 = 256;
    ep5_lut_menu_init(&menu);
    assert(ep5_lut_menu_begin_load(&menu,11) && ep5_lut_menu_publish(&menu,11,slots));
#define PRESS(key) ep5_wheel_controls_event(&editor,&menu,mount,key,&saved)
    assert(PRESS(0x900c) == 2); /* Choose this look in the existing browser. */
    assert(PRESS(0x900c) == EP5_WHEEL_OPEN);
    assert(PRESS(0x9008) == 1 && editor.sector == 11);
    for (int i = 0; i < 4; ++i) assert(PRESS(0x900a) == 1);
    assert(PRESS(0x9006) == 1 && editor.field == EP5_WF_HUE);
    for (int i = 0; i < 20; ++i) assert(PRESS(0x900a) == 1);
    assert(PRESS(0x9006) == 1 && editor.field == EP5_WF_SAT);
    for (int i = 0; i < 20; ++i) assert(PRESS(0x9008) == 1);
    assert(PRESS(0x9006) == 1 && editor.field == EP5_WF_LIGHT);
    for (int i = 0; i < 20; ++i) assert(PRESS(0x9008) == 1);
    assert(ep5_wheel_page(&editor,&menu,mount,&page));
    assert(page.sector == 3 && !strcmp(page.sector_name,"Red") && page.look_name[0]=='G');
    assert(page.hue == 15 && page.saturation == -5 && page.light == -15);
    for (int i = 0; i < 3; ++i) assert(PRESS(0x9006) == 1);
    assert(PRESS(0x900c) == EP5_WHEEL_SAVED);
    assert(saved.values.axis[0][3] == 15 && saved.values.axis[1][3] == -5);

    uint8_t bytes[EP5_WHEEL_FILE_BYTES];
    assert(ep5_wheel_encode(&saved,bytes,sizeof bytes));
    assert(ep5_wheel_decode(bytes,sizeof bytes,&loaded));
    assert(ep5_wheel_same_look(&saved,&loaded));
    assert(!memcmp(&saved.values,&loaded.values,sizeof saved.values));
    assert(bytes[12]==0x78 && bytes[15]==0x12 && bytes[16+3]==15 && bytes[16+12+3]==251);
    bytes[16] ^= 1;
    assert(!ep5_wheel_decode(bytes,sizeof bytes,&loaded) && loaded.values.axis[0][3]==15);
    assert(!ep5_wheel_decode(bytes,sizeof bytes-1,&loaded));

    assert(PRESS(0x900c) == EP5_WHEEL_OPEN); /* Undo reset with BACK. */
    assert(PRESS(0x9004) == 1 && PRESS(0x9004) == 1 && editor.field == EP5_WF_RESET_ALL);
    assert(PRESS(0x900c) == 1 && editor.draft.values.axis[0][3] == 0);
    assert(PRESS(0x9016) == EP5_WHEEL_CANCELLED && saved.values.axis[0][3]==15);
    assert(PRESS(0x900c) == EP5_WHEEL_OPEN && editor.draft.values.axis[0][3]==15);
    /* Clear yellow only. Red is a different sector and must remain edited. */
    for (int i=0;i<4;++i) assert(PRESS(0x9006)==1);
    assert(editor.field==EP5_WF_RESET_SECTOR);
    assert(PRESS(0x900c)==1 && editor.draft.values.axis[0][3]==15);
    for (int i=0;i<3;++i) assert(PRESS(0x9006)==1);
    for (int i=0;i<3;++i) assert(PRESS(0x900a)==1);
    for (int i=0;i<4;++i) assert(PRESS(0x9006)==1);
    assert(PRESS(0x900c)==1 && editor.draft.values.axis[0][3]==0);
    assert(PRESS(0x9016)==EP5_WHEEL_CANCELLED && saved.values.axis[0][3]==15);
    assert(PRESS(0x900c)==EP5_WHEEL_OPEN);
    ++mount;
    assert(!ep5_wheel_page(&editor,&menu,mount,&page) && !page.look_name[0]);
    assert(PRESS(0x900c) == EP5_WHEEL_STALE && saved.values.axis[0][3]==15);
    assert(PRESS(0x900c) == EP5_WHEEL_OPEN);
    ++menu.generation;
    assert(PRESS(0x900c) == EP5_WHEEL_STALE);
    assert(PRESS(0x900c) == EP5_WHEEL_OPEN);
    ++menu.slots[3].look_crc;
    assert(PRESS(0x900c) == EP5_WHEEL_STALE);
    assert(PRESS(0x900c) == EP5_WHEEL_OPEN && !editor.draft.values.axis[0][3]);
    ep5_lut_menu_begin_load(&menu,800);
    assert(PRESS(0x900c) == EP5_WHEEL_STALE);
}

static void check_bake(void)
{
    struct ep5_wheel_values v = {0};
    assert(ep5_wheel_bake(&v,0,0,base,EP5_LUT_VALUES,0,EP5_WHEEL_NODES));
    assert(base[3]==4096 && base[17*3+1]==4096 && base[289*3+2]==4096);
    assert(base[EP5_LUT_VALUES-1]==65535);
    v.axis[0][3]=3;
    for (unsigned first=0; first<EP5_WHEEL_NODES; first+=37) {
        unsigned remaining=EP5_WHEEL_NODES-first;
        assert(ep5_wheel_bake(&v,base,EP5_LUT_VALUES,table,EP5_LUT_VALUES,first,remaining<37?remaining:37));
    }
    uint8_t rgb[] = {176,96,96, 96,176,96, 128,128,128};
    assert(ep5_lut_rgb8(rgb,sizeof rgb,3,1,9,table,EP5_LUT_VALUES)==0);
    assert(rgb[1] > rgb[2]+5 && rgb[3]==96 && rgb[4]==176 && rgb[5]==96 && rgb[6]==128);
    assert(ep5_wheel_bake(&v,base,EP5_LUT_VALUES,base,EP5_LUT_VALUES,0,EP5_WHEEL_NODES));
    assert(memcmp(table,base,sizeof table)==0);
    assert(!ep5_wheel_bake(&v,base,EP5_LUT_VALUES,base+1,EP5_LUT_VALUES,0,1));
    assert(!ep5_wheel_bake(&v,0,0,base,EP5_LUT_VALUES,EP5_WHEEL_NODES,1));
    v.axis[0][3]=16;
    assert(!ep5_wheel_bake(&v,0,0,base,EP5_LUT_VALUES,0,1));
}

int main(int argc, char **argv)
{
    if (argc==2 && !strcmp(argv[1],"--rgb16le")) {
        struct ep5_wheel_values v;
        if (fread(v.axis,1,36,stdin)!=36 || !ep5_wheel_bake(&v,0,0,table,EP5_LUT_VALUES,0,EP5_WHEEL_NODES))
            return 1;
        for (unsigned i=0; i<EP5_LUT_VALUES; ++i) {
            putchar(table[i]&255);
            putchar(table[i]>>8);
        }
        return ferror(stdout)!=0;
    }
    check_editor();
    check_bake();
    return 0;
}
