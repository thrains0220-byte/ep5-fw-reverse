#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lut_wheel_draw.h"

struct trace { unsigned fills, texts; int emit; };
static void fill(void *ctx, unsigned x, unsigned y, unsigned w, unsigned h, uint32_t rgb)
{
    struct trace *t=ctx;
    assert(w && h && x+w<=42 && y+h<=13 && rgb<=0xffffff);
    ++t->fills;
    if (t->emit) printf("F %u %u %u %u %06x\n",x,y,w,h,(unsigned)rgb);
}
static void text(void *ctx, unsigned x, unsigned y, const uint16_t *str, uint32_t rgb)
{
    struct trace *t=ctx;
    unsigned width=0;
    ++t->texts;
    if (t->emit) printf("T %u %u %06x",x,y,(unsigned)rgb);
    for (unsigned i=0; str[i]; ++i) {
        width += str[i]<128 ? 1u : 2u;
        if (t->emit) printf(" %04x",(unsigned)str[i]);
    }
    assert(width && x+width<=42 && y<13);
    if (t->emit) putchar('\n');
}
int main(int argc, char **argv)
{
    struct ep5_wheel_editor e={0};
    struct ep5_wheel_edit saved={0};
    struct ep5_lut_menu menu;
    struct ep5_lut_menu_slot slots[EP5_LUT_MENU_SLOTS]={0};
    struct trace t={0};
    struct ep5_wheel_surface surface={&t,42,13,fill,text};
    t.emit=argc==2 && !strcmp(argv[1],"--trace");
    slots[0].picture_mode=103; slots[0].variant=1; slots[0].number=1;
    slots[0].configured=1; slots[0].amount_q8=256; slots[0].look_crc=123;
    const char name[]="Gold";
    for (unsigned i=0;i<sizeof name;++i) slots[0].label[i]=(uint16_t)name[i];
    ep5_lut_menu_init(&menu);
    assert(ep5_lut_menu_begin_load(&menu,10) && ep5_lut_menu_publish(&menu,10,slots));
#define PRESS(k) ep5_wheel_controls_event(&e,&menu,5,k,&saved)
    assert(PRESS(0x900c)==2 && PRESS(0x900c)==EP5_WHEEL_OPEN);
    assert(PRESS(0x900a)==1 && PRESS(0x900a)==1 && PRESS(0x900a)==1);
    assert(PRESS(0x9006)==1 && PRESS(0x900a)==1 && PRESS(0x900a)==1);
    assert(PRESS(0x9006)==1 && PRESS(0x9008)==1 && PRESS(0x9008)==1);
    assert(ep5_wheel_draw(&e,&menu,5,&surface));
    assert(t.fills==16 && t.texts==16);
    surface.columns=41;
    assert(!ep5_wheel_draw(&e,&menu,5,&surface));
    surface.columns=42;
    assert(!ep5_wheel_draw(&e,&menu,6,&surface));
    assert(t.fills==16 && t.texts==16);
    return 0;
}
