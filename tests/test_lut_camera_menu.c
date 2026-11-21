#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "lut_camera_menu.h"

static unsigned opened, closed;
static void *open_file(void *ctx, const char *path)
{
    (void)ctx;
    FILE *fp=fopen(path,"rb");
    opened+=fp!=NULL;
    return fp;
}
static int32_t read_file(void *ctx, void *fp, uint8_t *out, uint32_t size)
{
    (void)ctx;
    size_t n=fread(out,1,size,fp);
    return ferror(fp)?-1:(int32_t)n;
}
static int close_file(void *ctx, void *fp)
{
    (void)ctx;
    ++closed;
    return fclose(fp);
}
static struct ep5_camera_menu ui;
static struct ep5_camera_choice choice;
static int press(uint16_t key) { return ep5_camera_menu_event(&ui,17,key); }
static int shoot(void) { return ep5_camera_menu_capture(&ui,17,&choice); }
static int finish(uint32_t mount)
{
    for (unsigned i=0;i<100;++i) {
        int status=ep5_camera_menu_step(&ui,mount);
        if (status!=EP5_LUT_JOB_BUSY) return status;
    }
    return -99;
}
static void open_group(void)
{
    assert(press(0x900c)==EP5_CAMERA_LOAD_GROUP && !shoot());
    assert(finish(17)==EP5_LUT_JOB_INDEX_READY);
}
static void next_group(void)
{
    assert(press(0x9014)==EP5_CAMERA_SHOW_GROUPS);
    assert(press(0x9006)==1);
    open_group();
}
static void select_and_edit(void)
{
    assert(press(0x900c)==2 && shoot());
    assert(press(0x900c)==EP5_WHEEL_OPEN);
    assert(press(0x9006)==1 && press(0x900a)==1); /* hue yellow +1 */
    for (int i=0;i<5;++i) assert(press(0x9006)==1);
    assert(press(0x900c)==EP5_WHEEL_SAVED && shoot());
    assert(choice.has_wheel && choice.wheel.axis[EP5_WHEEL_HUE][0]==1);
}
static void duplicate_groups(void)
{
    open_group();
    select_and_edit();
    struct ep5_camera_choice original = choice;
    assert(ep5_camera_menu_choice_current(&ui,17,&original));
    uint32_t crc=choice.look.look_crc;
    next_group();
    assert(!shoot());
    assert(press(0x900c)==2 && shoot() && choice.bank==2);
    assert(choice.look.look_crc==crc && !choice.has_wheel);
    assert(!ep5_camera_menu_choice_current(&ui,17,&original));
    assert(press(0x900c)==EP5_WHEEL_OPEN && !ui.wheel.draft.values.axis[EP5_WHEEL_HUE][0]);
    assert(press(0x9014)==EP5_WHEEL_CANCELLED);
    assert(press(0x9014)==EP5_CAMERA_SHOW_GROUPS && press(0x9004)==1);
    open_group();
    assert(press(0x900c)==2 && shoot() && choice.bank==1 && choice.has_wheel);
    assert(!ep5_camera_menu_choice_current(&ui,17,&original));
    assert(ep5_camera_menu_choice_current(&ui,17,&choice));
}
static void cancellation(void)
{
    assert(press(0x900c)==EP5_CAMERA_LOAD_GROUP);
    assert(ep5_camera_menu_step(&ui,17)==EP5_LUT_JOB_BUSY);
    assert(ep5_camera_menu_step(&ui,17)==EP5_LUT_JOB_BUSY && opened==1);
    assert(press(0x9014)==EP5_CAMERA_SHOW_GROUPS && press(0x9006)==1);
    open_group(); /* Waits for the interrupted read to close before opening B02. */
    assert(opened==closed && ui.group_focus==2);
    assert(press(0x900c)==2 && shoot() && choice.bank==2);
    assert(ep5_camera_menu_event(&ui,16,0x9014)==0 && shoot()); /* old event */
    assert(!ep5_camera_menu_capture(&ui,16,&choice));
    assert(press(0x9014)==EP5_CAMERA_SHOW_GROUPS && press(0x9006)==1);
    assert(press(0x900c)==EP5_CAMERA_LOAD_GROUP);
    assert(ep5_camera_menu_step(&ui,17)==EP5_LUT_JOB_BUSY);
    assert(ep5_camera_menu_step(&ui,17)==EP5_LUT_JOB_BUSY);
    assert(finish(0)==EP5_LUT_JOB_CANCELLED && opened==closed && !shoot());
}
static void all_looks(void)
{
    for (unsigned g=1; g<=3; ++g) {
        if (g==1) open_group(); else next_group();
        unsigned count=g==3?1:14;
        for (unsigned i=0;i<count;++i) {
            assert(press(0x900c)==2 && shoot() && choice.bank==g && choice.mount==17);
            const struct ep5_lut_menu_slot *slot=&ui.looks.slots[ui.looks.applied-1];
            printf("%u %u %u %u %08x ",g,choice.look.number,choice.look.picture_mode,
                   choice.look.variant,(unsigned)choice.look.look_crc);
            for (unsigned k=0; k<6 && slot->label[k]; ++k) putchar(slot->label[k]);
            putchar('\n');
            assert(press(0x9006)==1);
        }
    }
    assert(press(0x9014)==EP5_CAMERA_SHOW_GROUPS && press(0x9014)==3);
    assert(shoot() && choice.bank==3 && ep5_camera_menu_open(&ui,17)==EP5_CAMERA_SHOW_GROUPS);
}
static void trace_fill(void *ctx,unsigned x,unsigned y,unsigned w,unsigned h,uint32_t color)
{
    (void)ctx;
    assert(w && h && x+w<=42 && y+h<=13);
    printf("F %u %u %u %u %06x\n",x,y,w,h,(unsigned)color);
}
static void trace_text(void *ctx,unsigned x,unsigned y,const uint16_t *str,uint32_t color)
{
    (void)ctx;
    unsigned width=0;
    printf("T %u %u %06x",x,y,(unsigned)color);
    while (*str) {
        width += *str<128 ? 1u : 2u;
        printf(" %04x",(unsigned)*str++);
    }
    assert(width && x+width<=42 && y<13);
    putchar('\n');
}
static void draw_page(int looks)
{
    struct ep5_wheel_surface surface={NULL,42,13,trace_fill,trace_text};
    assert(press(0x9006)==1);
    if (looks) {
        open_group();
        assert(press(0x900c)==2 && press(0x9006)==1);
    }
    assert(ep5_camera_menu_draw(&ui,17,&surface));
}

/* Reference file worker for a single-owner host directory. Rename publishes
 * the staged sibling without deleting the previous file. Failure injection
 * happens after staging; restarting the process simulates loss of all RAM. */
static unsigned load_calls, replace_calls, fail_commit, revoke_at_commit;
static uint32_t fixture_mount;
static int load_edit(void *ctx, uint32_t mount, const char *path, uint8_t bytes[EP5_WHEEL_FILE_BYTES])
{
    (void)ctx;
    ++load_calls;
    if (mount!=fixture_mount) return -1;
    FILE *fp=fopen(path,"rb");
    if (!fp) return errno==ENOENT?0:-1;
    int valid=fread(bytes,1,EP5_WHEEL_FILE_BYTES,fp)==EP5_WHEEL_FILE_BYTES &&
              fgetc(fp)==EOF && !ferror(fp);
    return fclose(fp)==0 && valid ? 1 : -1;
}
static int replace_edit(void *ctx, uint32_t mount, const char *path, const uint8_t bytes[EP5_WHEEL_FILE_BYTES])
{
    (void)ctx;
    ++replace_calls;
    if (mount!=fixture_mount) return 0;
    char staged[40];
    int n=snprintf(staged,sizeof staged,"%s.tmp",path);
    assert(n>0 && (size_t)n<sizeof staged);
    FILE *fp=fopen(staged,"wb");
    if (!fp) return 0;
    int written=fwrite(bytes,1,EP5_WHEEL_FILE_BYTES,fp)==EP5_WHEEL_FILE_BYTES;
    if (revoke_at_commit) ++fixture_mount;
    if (fclose(fp)==0 && written && !fail_commit && mount==fixture_mount && rename(staged,path)==0)
        return 1;
    assert(remove(staged)==0);
    return 0;
}
static void queue_edit(void)
{
    unsigned reads=load_calls, writes=replace_calls;
    assert(press(0x900c)==EP5_WHEEL_OPEN);
    assert(press(0x9006)==1 && press(0x900a)==1);
    for (unsigned i=0;i<5;++i) assert(press(0x9006)==1);
    assert(press(0x900c)==EP5_CAMERA_SAVE_REQUEST);
    assert(load_calls==reads && replace_calls==writes);
}
static int value_now(void)
{
    assert(shoot());
    return choice.has_wheel ? choice.wheel.axis[EP5_WHEEL_HUE][0] : 0;
}
static int dial(enum ep5_camera_dial knob, int ticks)
{
    return ep5_camera_menu_dial(&ui,17,ep5_camera_menu_foreground(&ui,17),knob,(int16_t)ticks);
}

static void dial_controls(void)
{
    assert(!dial(EP5_CAMERA_MAIN_DIAL,0) && !dial((enum ep5_camera_dial)9,1));
    assert(dial(EP5_CAMERA_MAIN_DIAL,2) && ui.group_focus==3);
    assert(dial(EP5_CAMERA_SUB_DIAL,1) && ui.group_focus==3);
    assert(dial(EP5_CAMERA_MAIN_DIAL,-2) && ui.group_focus==1);
    open_group();
    assert(press(0x900c)==2 && shoot());
    unsigned first=ui.looks.cursor;
    uint16_t number=choice.look.number;
    assert(dial(EP5_CAMERA_MAIN_DIAL,1) && ui.looks.cursor!=first);
    assert(shoot() && choice.look.number==number);
    assert(dial(EP5_CAMERA_MAIN_DIAL,-1) && ui.looks.cursor==first);
    assert(dial(EP5_CAMERA_SUB_DIAL,INT16_MIN) && ui.looks.amount_q8==0);
    assert(shoot() && choice.look.amount_q8==256);
    assert(dial(EP5_CAMERA_MAIN_DIAL,14) && ui.looks.amount_q8==256 && ui.looks.cursor==first);
    assert(dial(EP5_CAMERA_SUB_DIAL,-2) && press(0x900c)==2 && shoot() && choice.look.amount_q8==224);
    assert(press(0x900c)==EP5_WHEEL_OPEN);
    assert(dial(EP5_CAMERA_MAIN_DIAL,-1) && ui.wheel.sector==11);
    assert(dial(EP5_CAMERA_SUB_DIAL,INT16_MAX) && ui.wheel.field==EP5_WF_HUE &&
           ui.wheel.draft.values.axis[0][11]==15);
    assert(press(0x9006)==1 && dial(EP5_CAMERA_SUB_DIAL,INT16_MIN) && ui.wheel.draft.values.axis[1][11]==-5);
    assert(press(0x9006)==1 && dial(EP5_CAMERA_SUB_DIAL,2) && ui.wheel.draft.values.axis[2][11]==2);
    assert(dial(EP5_CAMERA_MAIN_DIAL,2) && ui.wheel.sector==1 && ui.wheel.field==EP5_WF_LIGHT);
    assert(dial(EP5_CAMERA_SUB_DIAL,-1) && ui.wheel.draft.values.axis[2][1]==-1);
    assert(press(0x9006)==1 && dial(EP5_CAMERA_SUB_DIAL,12) && ui.wheel.field==EP5_WF_RESET_SECTOR);
    assert(press(0x9006)==1 && press(0x9006)==1 && dial(EP5_CAMERA_SUB_DIAL,1));
    assert(shoot() && !choice.has_wheel && press(0x900c)==EP5_WHEEL_SAVED);
    assert(shoot() && choice.has_wheel && choice.wheel.axis[0][11]==15 && choice.wheel.axis[2][1]==-1);
}

static void release_controls(enum ep5_camera_release reason)
{
    open_group();
    select_and_edit();
    uint16_t number=choice.look.number;
    uint32_t focus=ui.foreground;
    assert(press(0x900c)==EP5_WHEEL_OPEN && dial(EP5_CAMERA_SUB_DIAL,8));
    ep5_camera_menu_release(&ui,16,focus,reason);
    ep5_camera_menu_release(&ui,17,focus,(enum ep5_camera_release)99);
    assert(ui.wheel.active);
    ep5_camera_menu_release(&ui,17,focus,reason);
    assert(ui.page==EP5_CAMERA_CLOSED && !ui.wheel.active && value_now()==1);
    assert(!dial(EP5_CAMERA_MAIN_DIAL,1) && !ep5_camera_menu_key(&ui,17,0,0x900c));
    assert(ep5_camera_menu_key(&ui,17,focus,0x900c)==EP5_CAMERA_KEY_CONSUMED);
    assert(ep5_camera_menu_open(&ui,17)==EP5_CAMERA_SHOW_GROUPS);
    ep5_camera_menu_release(&ui,17,focus,reason);
    assert(ui.page==EP5_CAMERA_GROUPS && ep5_camera_menu_key(&ui,17,focus,0x900c)==EP5_CAMERA_KEY_CONSUMED &&
           ep5_camera_menu_dial(&ui,17,focus,EP5_CAMERA_MAIN_DIAL,1) && ui.group_focus==1);
    assert(!ep5_camera_menu_dial(&ui,17,0,EP5_CAMERA_MAIN_DIAL,1));
    assert(ep5_camera_menu_key(&ui,17,ui.foreground,0xffff)==0);
    assert(dial(EP5_CAMERA_MAIN_DIAL,1) && press(0x900c)==EP5_CAMERA_LOAD_GROUP);
    assert(ep5_camera_menu_step(&ui,17)==EP5_LUT_JOB_BUSY); /* pending other bank */
    ep5_camera_menu_release(&ui,17,ui.foreground,reason);
    assert(value_now()==1 && choice.bank==1 && choice.look.number==number &&
           ep5_camera_menu_choice_current(&ui,17,&choice));
    assert(finish(17)==EP5_LUT_JOB_CANCELLED && value_now()==1);
}

static void release_save(const char *operation, int expected)
{
    queue_edit();
    unsigned reads=load_calls, writes=replace_calls;
    struct ep5_camera_wheel_job dispatched;
    int queued=!strcmp(operation,"release-queued");
    if (!queued) {
        assert(ep5_camera_wheel_take(&ui,17,&dispatched));
        assert(ep5_camera_menu_key(&ui,17,ui.foreground,0x900c)==EP5_CAMERA_KEY_CONSUMED);
    }
    ep5_camera_menu_release(&ui,17,ui.foreground,EP5_CAMERA_HALF_SHUTTER);
    assert(ui.page==EP5_CAMERA_CLOSED && !ui.wheel.active && value_now()==expected);
    assert(reads==load_calls && writes==replace_calls && !dial(EP5_CAMERA_SUB_DIAL,1));
    if (queued) {
        assert(!ep5_camera_wheel_take(&ui,17,&dispatched));
        return;
    }
    assert(ep5_camera_menu_open(&ui,17)==EP5_CAMERA_SHOW_GROUPS && press(0x900c)==EP5_CAMERA_LOAD_GROUP);
    assert(ep5_camera_menu_step(&ui,17)==EP5_LUT_JOB_BUSY && load_calls==reads);
    fail_commit=!strcmp(operation,"release-fail");
    int result=ep5_camera_wheel_execute(&dispatched);
    assert(result==(fail_commit ? 0 : 1) && replace_calls==writes+1);
    assert(ep5_camera_wheel_finish(&ui,17,&dispatched,result)==EP5_LUT_JOB_CANCELLED);
    assert(!ui.wheel.active && finish(17)==EP5_LUT_JOB_INDEX_READY);
    assert(press(0x900c)==2 && value_now()==expected+!fail_commit);
}
static void persistence(const char *operation, unsigned bank, int expected)
{
    struct ep5_camera_wheel_store store={NULL,load_edit,replace_edit};
    fixture_mount=17;
    assert(ep5_camera_menu_attach_store(&ui,&store));
    if (bank==2) assert(press(0x9006)==1);
    open_group();
    assert(load_calls && !replace_calls);
    assert(press(0x900c)==2 && value_now()==expected);
    struct ep5_camera_choice before=choice;
    if (!strcmp(operation,"read")) return;
    if (!strncmp(operation,"release-",8)) { release_save(operation,expected); return; }
    if (!strcmp(operation,"damaged")) {
        assert(ui.unreadable_edits & (1u<<ui.looks.cursor));
        return;
    }
    if (!strcmp(operation,"clean")) {
        assert(!(ui.unreadable_edits & (1u<<ui.looks.cursor)));
        return;
    }
    if (!strcmp(operation,"late-read")) {
        struct ep5_camera_wheel_job cancelled, fresh;
        assert(press(0x9014)==EP5_CAMERA_SHOW_GROUPS && press(0x900c)==EP5_CAMERA_LOAD_GROUP);
        while (!ui.restore_next) assert(ep5_camera_menu_step(&ui,17)==EP5_LUT_JOB_BUSY);
        assert(ep5_camera_wheel_take(&ui,17,&cancelled) && !cancelled.write);
        int old_result=ep5_camera_wheel_execute(&cancelled);
        assert(press(0x9014)==EP5_CAMERA_SHOW_GROUPS && press(0x900c)==EP5_CAMERA_LOAD_GROUP);
        while (!ui.restore_next) assert(ep5_camera_menu_step(&ui,17)==EP5_LUT_JOB_BUSY);
        assert(ep5_camera_wheel_take(&ui,17,&fresh) && !fresh.write);
        assert(ep5_camera_wheel_finish(&ui,17,&cancelled,old_result)==EP5_LUT_JOB_CANCELLED);
        assert(ep5_camera_wheel_finish(&ui,17,&fresh,ep5_camera_wheel_execute(&fresh))==EP5_LUT_JOB_BUSY);
        assert(finish(17)==EP5_LUT_JOB_INDEX_READY && press(0x900c)==2);
        assert(value_now()==expected);
        return;
    }
    queue_edit();
    assert(value_now()==expected && ep5_camera_menu_choice_current(&ui,17,&before));
    if (!strcmp(operation,"worker-write") || !strcmp(operation,"worker-eject")) {
        struct ep5_camera_wheel_job job, duplicate;
        assert(ep5_camera_wheel_take(&ui,17,&job) && job.write);
        assert(!ep5_camera_wheel_take(&ui,17,&duplicate) && !replace_calls);
        assert(press(0x9014)==0 && value_now()==expected); /* Atomic commit already dispatched. */
        if (!strcmp(operation,"worker-eject")) {
            assert(ep5_camera_menu_event(&ui,0,0)==0);
            fixture_mount=18;
            int result=ep5_camera_wheel_execute(&job);
            assert(result==0 && ep5_camera_wheel_finish(&ui,18,&job,result)==EP5_LUT_JOB_CANCELLED);
            assert(!shoot());
            return;
        }
        int result=ep5_camera_wheel_execute(&job);
        assert(result==1 && replace_calls==1 && value_now()==expected);
        assert(ep5_camera_wheel_finish(&ui,17,&job,result)==EP5_CAMERA_SAVE_COMPLETE);
        assert(ep5_camera_wheel_finish(&ui,17,&job,result)==EP5_LUT_JOB_CANCELLED);
        assert(value_now()==expected+1);
    } else if (!strcmp(operation,"cancel")) {
        assert(press(0x9014)==EP5_WHEEL_CANCELLED);
        (void)finish(17);
        assert(!replace_calls && value_now()==expected);
    } else if (!strcmp(operation,"eject")) {
        fixture_mount=18;
        assert(ep5_camera_menu_step(&ui,18)==EP5_LUT_JOB_CANCELLED && !replace_calls);
        assert(ep5_camera_menu_event(&ui,0,0)==0);
        (void)finish(0);
        assert(!replace_calls && !shoot());
    } else if (!strcmp(operation,"rebound")) {
        fixture_mount=18;
        assert(ep5_camera_menu_step(&ui,17)==EP5_LUT_JOB_ERROR);
        assert(replace_calls==1 && value_now()==expected);
    } else if (!strcmp(operation,"commit-eject")) {
        revoke_at_commit=1;
        assert(ep5_camera_menu_step(&ui,17)==EP5_LUT_JOB_ERROR);
        assert(replace_calls==1 && fixture_mount==18 && value_now()==expected);
        assert(ep5_camera_menu_event(&ui,0,0)==0 && !shoot());
    } else {
        if (!strcmp(operation,"retry") || !strcmp(operation,"fail")) {
            fail_commit=1;
            assert(finish(17)==EP5_LUT_JOB_ERROR && ui.wheel.active);
            assert(replace_calls==1 && value_now()==expected);
            assert(ep5_camera_menu_choice_current(&ui,17,&before));
            if (!strcmp(operation,"fail")) {
                assert(press(0x9014)==EP5_WHEEL_CANCELLED);
                return;
            }
            fail_commit=0;
            assert(press(0x900c)==EP5_CAMERA_SAVE_REQUEST);
        } else assert(!strcmp(operation,"write"));
        assert(finish(17)==EP5_CAMERA_SAVE_COMPLETE);
        assert(value_now()==expected+1 && !ep5_camera_menu_choice_current(&ui,17,&before));
    }
}
int main(int argc, char **argv)
{
    struct ep5_look_io card={NULL,open_file,read_file,close_file};
    assert(ep5_camera_menu_init(&ui,&card,17));
    if (argc==2 && !strcmp(argv[1],"--dials")) dial_controls();
    else if (argc==3 && !strcmp(argv[1],"--release")) release_controls((enum ep5_camera_release)atoi(argv[2]));
    else if (argc==5 && !strcmp(argv[1],"--persist"))
        persistence(argv[2],(unsigned)atoi(argv[3]),atoi(argv[4]));
    else if (argc==2 && !strcmp(argv[1],"--duplicate")) duplicate_groups();
    else if (argc==2 && !strcmp(argv[1],"--cancel")) cancellation();
    else if (argc==2 && !strcmp(argv[1],"--trace-groups")) draw_page(0);
    else if (argc==2 && !strcmp(argv[1],"--trace-looks")) draw_page(1);
    else all_looks();
    assert(opened==closed);
    return 0;
}
