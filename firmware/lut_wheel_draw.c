#include "lut_wheel_draw.h"

enum { BACKGROUND=0x15202a, PANEL=0x1e2c39, WHITE=0xf2f5f6, MUTED=0xb4c2cc, FOCUS=0x355a70 };
static const wchar_t *const sectors[] = {
    L"黄",L"橙",L"橙红",L"红",L"品红",L"紫",L"蓝",L"蓝青",L"青",L"绿青",L"绿",L"黄绿"
};
static const wchar_t *const field_names[] = {
    L"色区",L"色相",L"饱和度",L"明度",L"重置本色",L"重置全部",L"保存调整"
};
static const uint32_t swatches[] = {
    0xeac747,0xfca852,0xfa755b,0xe54e56,0xd456ae,0xa06ad7,
    0x688fe0,0x58ade6,0x44c5ca,0x45b995,0x78bc69,0xb4c054
};
static const uint8_t ring[][2] = {
    {9,2},{13,2},{16,3},{17,5},{16,7},{13,8},
    {9,9},{5,8},{2,7},{1,5},{2,3},{5,2}
};

static void caption(const struct ep5_wheel_surface *s, unsigned x, unsigned y,
                    const wchar_t *source, uint32_t color)
{
    uint16_t text[28];
    unsigned n = 0;
    while (source[n] && n+1 < sizeof text / sizeof text[0]) {
        text[n] = (uint16_t)source[n];
        ++n;
    }
    text[n] = 0;
    s->text(s->ctx,x,y,text,color);
}

static void value(const struct ep5_wheel_surface *s, unsigned row, int number)
{
    unsigned n=0, absolute=(unsigned)(number<0 ? -number : number);
    uint16_t text[4];
    if (number) text[n++]=(uint16_t)(number<0 ? '-' : '+');
    if (absolute>=10) text[n++]=(uint16_t)('0'+absolute/10);
    text[n++]=(uint16_t)('0'+absolute%10);
    text[n]=0;
    s->text(s->ctx,36,row,text,WHITE);
}

int ep5_wheel_draw(const struct ep5_wheel_editor *editor, const struct ep5_lut_menu *menu,
                   uint32_t mount, const struct ep5_wheel_surface *s)
{
    struct ep5_wheel_page page;
    if (!s || !s->text || !s->fill || s->columns<42 || s->rows<13 ||
        !ep5_wheel_page(editor,menu,mount,&page))
        return 0;
    s->fill(s->ctx,0,0,42,13,BACKGROUND);
    caption(s,1,0,L"胶片色轮",WHITE);
    /* Protocol 2 lookup names contain at most six BMP glyphs. Also bound
     * stale or synthetic callers' labels to reserve space at native size. */
    page.look_name[6]=0;
    s->text(s->ctx,27,0,page.look_name,MUTED);
    s->fill(s->ctx,21,2,21,8,PANEL);
    for (unsigned i=0; i<12; ++i) {
        unsigned x=ring[i][0], y=ring[i][1];
        if (i==page.sector) {
            s->fill(s->ctx,x-1,y,4,1,WHITE);
        }
        s->fill(s->ctx,x,y,2,1,swatches[i]);
    }
    caption(s,8,5,sectors[page.sector],WHITE);
    for (unsigned i=0; i<EP5_WF_COUNT; ++i) {
        unsigned y=2+i;
        if (i==page.field) s->fill(s->ctx,21,y,21,1,FOCUS);
        caption(s,23,y,field_names[i],WHITE);
        if (i==EP5_WF_SECTOR) caption(s,36,y,sectors[page.sector],WHITE);
        if (i==EP5_WF_HUE) value(s,y,page.hue);
        if (i==EP5_WF_SAT) value(s,y,page.saturation);
        if (i==EP5_WF_LIGHT) value(s,y,page.light);
    }
    caption(s,1,11,L"上下选项   左右调整",MUTED);
    caption(s,1,12,L"OK 确认   MENU 取消",MUTED);
    return 1;
}
