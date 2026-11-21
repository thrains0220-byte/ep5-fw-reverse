#include "lut_camera_menu.h"
#include "object_bytes.h"

static int valid_mount(const struct ep5_camera_menu *ui, uint32_t mount)
{
    return ui && mount && mount==ui->mount;
}

static void change_revision(struct ep5_camera_menu *ui)
{
    if (++ui->revision == 0)
        ui->revision = 1;
}

int ep5_camera_menu_init(struct ep5_camera_menu *ui, const struct ep5_look_io *io, uint32_t mount)
{
    if (!ui || !mount || !ep5_lut_bank_browser_init(&ui->browser,io))
        return 0;
    ep5_lut_menu_init(&ui->looks);
    for (unsigned g=0; g<EP5_LUT_BANK_COUNT; ++g)
        for (unsigned i=0; i<EP5_LUT_MENU_SLOTS; ++i)
            ui->saved[g][i].number=0;
    ui->wheel.active=0;
    ui->mount=mount;
    ui->revision=1;
    ui->group_focus=1;
    ui->pending=0;
    ui->store.load=0;
    ui->restore_next=0;
    ui->unreadable_edits=0;
    ui->wheel_write=EP5_CAMERA_WRITE_IDLE;
    ui->wheel_ticket=0;
    ui->wheel_inflight=0;
    ui->finishing_write=0;
    ui->foreground=1;
    ui->confirmed.mount=0;
    ui->page=EP5_CAMERA_GROUPS;
    return 1;
}

int ep5_camera_menu_attach_store(struct ep5_camera_menu *ui, const struct ep5_camera_wheel_store *store)
{
    if (!ui || !ui->mount || ui->page!=EP5_CAMERA_GROUPS || ui->browser.selected ||
        ui->store.load || !store || !store->load || !store->replace) return 0;
    ui->store=*store;
    return 1;
}

int ep5_camera_menu_open(struct ep5_camera_menu *ui, uint32_t mount)
{
    if (!valid_mount(ui,mount) || ui->page!=EP5_CAMERA_CLOSED)
        return 0;
    if (++ui->foreground==0) ++ui->foreground;
    ui->page=EP5_CAMERA_GROUPS;
    return EP5_CAMERA_SHOW_GROUPS;
}

static void leave_list(struct ep5_camera_menu *ui)
{
    ui->wheel.active=0;
    ui->wheel_inflight=0;
    ui->wheel_write=EP5_CAMERA_WRITE_IDLE;
    ui->restore_next=0;
    ui->pending=0;
    (void)ep5_lut_menu_event(&ui->looks,EP5_LUT_MENU_BACK);
    ui->page=EP5_CAMERA_GROUPS;
}

static void eject(struct ep5_camera_menu *ui)
{
    if (ui && ui->mount) {
        leave_list(ui);
        ui->looks.applied=0;
        ui->page=EP5_CAMERA_CLOSED;
        ui->mount=0;
        ui->confirmed.mount=0;
        ui->finishing_write=0;
    }
}

static int owns_input(const struct ep5_camera_menu *ui, uint32_t mount, uint32_t foreground)
{
    return valid_mount(ui,mount) && ui->page!=EP5_CAMERA_CLOSED && foreground==ui->foreground;
}

uint32_t ep5_camera_menu_foreground(const struct ep5_camera_menu *ui, uint32_t mount)
{
    return valid_mount(ui,mount) && ui->page!=EP5_CAMERA_CLOSED ? ui->foreground : 0;
}

void ep5_camera_menu_release(struct ep5_camera_menu *ui, uint32_t mount, uint32_t foreground,
                             enum ep5_camera_release reason)
{
    if (!owns_input(ui,mount,foreground) || reason<EP5_CAMERA_FOCUS_LOST || reason>EP5_CAMERA_POWER_OFF)
        return;
    if (ui->wheel_inflight && ui->wheel_write==EP5_CAMERA_WRITE_QUEUED)
        ui->finishing_write=ui->wheel_ticket;
    leave_list(ui);
    ui->page=EP5_CAMERA_CLOSED;
}

int ep5_camera_menu_key(struct ep5_camera_menu *ui, uint32_t mount, uint32_t foreground, uint16_t key)
{
    if (!foreground) return 0;
    switch (key) {
    case 0x9004: case 0x9006: case 0x9008: case 0x900a:
    case 0x900c: case 0x900e: case 0x9012: case 0x9014: case 0x9016: {
        if (!owns_input(ui,mount,foreground)) return EP5_CAMERA_KEY_CONSUMED;
        int action=ep5_camera_menu_event(ui,mount,key);
        return action ? action : EP5_CAMERA_KEY_CONSUMED;
    }
    default:
        return 0;
    }
}

int ep5_camera_menu_dial(struct ep5_camera_menu *ui, uint32_t mount, uint32_t foreground,
                         enum ep5_camera_dial dial, int16_t detents)
{
    if (!foreground || !detents ||
        (dial!=EP5_CAMERA_MAIN_DIAL && dial!=EP5_CAMERA_SUB_DIAL)) return 0;
    if (!owns_input(ui,mount,foreground)) return 1;
    int steps=detents;
    if (ui->page==EP5_CAMERA_GROUPS) {
        if (dial==EP5_CAMERA_MAIN_DIAL) {
            int count=(int)EP5_LUT_BANK_COUNT;
            ui->group_focus=(uint8_t)(1+(ui->group_focus-1+steps%count+count)%count);
        }
        return 1;
    }
    if (ui->pending || ui->restore_next || ui->wheel_write==EP5_CAMERA_WRITE_QUEUED ||
        ui->looks.state!=EP5_LUT_MENU_READY) return 1;
    if (ui->wheel.active && dial==EP5_CAMERA_MAIN_DIAL) {
        int count=(int)EP5_WHEEL_SECTORS;
        ui->wheel.sector=(uint8_t)((ui->wheel.sector+steps%count+count)%count);
        return 1;
    }
    if (ui->wheel.active) {
        if (ui->wheel.field>EP5_WF_LIGHT) return 1;
        if (ui->wheel.field==EP5_WF_SECTOR) ui->wheel.field=EP5_WF_HUE;
        /* Each H/S/L axis saturates within at most 30 clicks. */
        if (steps>30) steps=30;
        if (steps< -30) steps= -30;
    } else if (dial==EP5_CAMERA_MAIN_DIAL) {
        int count=0;
        for (unsigned i=0;i<EP5_LUT_MENU_SLOTS;++i) count+=ui->looks.slots[i].configured!=0;
        if (!count) return 1;
        /* One complete circuit discards a pending slider edit on a multi-
         * look card, just as the same individual navigation events do. */
        if (count>1 && (steps>=count || steps<=-count))
            steps=steps%count+(steps>0 ? count : -count);
        if (count==1) return 1;
    } else {
        if (steps>16) steps=16;
        if (steps< -16) steps= -16;
    }
    uint16_t key=dial==EP5_CAMERA_MAIN_DIAL ? (steps>0 ? 0x9006 : 0x9004)
                                             : (steps>0 ? 0x900a : 0x9008);
    int ticks=steps>0 ? steps : -steps;
    for (int i=0;i<ticks;++i) (void)ep5_camera_menu_event(ui,mount,key);
    return 1;
}

int ep5_camera_menu_event(struct ep5_camera_menu *ui, uint32_t mount, uint16_t key)
{
    if (!valid_mount(ui,mount)) {
        if (!mount) eject(ui);
        return 0;
    }
    if (ui->page==EP5_CAMERA_CLOSED)
        return 0;
    int back=key==0x9014 || key==0x9016;
    int ok=key==0x900c || key==0x900e || key==0x9012;
    if (ui->page==EP5_CAMERA_GROUPS) {
        if (back) {
            ui->page=EP5_CAMERA_CLOSED;
            return 3;
        }
        if (ok) {
            change_revision(ui);
            ui->page=EP5_CAMERA_LOOKS;
            ui->pending=ui->group_focus;
            if (ui->store.load || ui->browser.selected!=ui->group_focus)
                ui->looks.applied=0;
            return EP5_CAMERA_LOAD_GROUP;
        }
        int direction=0;
        if (key==0x9004 || key==0x9008) direction=-1;
        if (key==0x9006 || key==0x900a) direction=1;
        if (!direction) return 0;
        ui->group_focus=(uint8_t)ep5_lut_bank_next(ui->group_focus,direction);
        return 1;
    }
    if (ui->wheel_write==EP5_CAMERA_WRITE_QUEUED) {
        if (!back || ui->wheel_inflight) return 0;
        ui->wheel_write=EP5_CAMERA_WRITE_IDLE;
        return EP5_WHEEL_CANCELLED;
    }
    if (back && !ui->wheel.active) {
        leave_list(ui);
        return EP5_CAMERA_SHOW_GROUPS;
    }
    if (ui->pending || ui->restore_next || ui->looks.state==EP5_LUT_MENU_LOADING)
        return 1;
    if (ui->looks.state==EP5_LUT_MENU_ERROR && ok) {
        ui->pending=ui->group_focus;
        return EP5_CAMERA_LOAD_GROUP;
    }
    if (!ui->browser.selected || ui->looks.cursor>=EP5_LUT_MENU_SLOTS)
        return 0;
    int queue_save=ui->store.load && ui->wheel.active && ui->wheel.field==EP5_WF_SAVE && ok;
    struct ep5_wheel_edit *saved=&ui->saved[ui->browser.selected-1][ui->looks.cursor];
    int result=ep5_wheel_controls_event(&ui->wheel,&ui->looks,mount,key,
        queue_save ? &ui->wheel.draft : saved);
    if (queue_save && result==EP5_WHEEL_SAVED) {
        ui->wheel_write=EP5_CAMERA_WRITE_QUEUED;
        return EP5_CAMERA_SAVE_REQUEST;
    }
    if (result==EP5_WHEEL_CANCELLED || result==EP5_WHEEL_OPEN)
        ui->wheel_write=EP5_CAMERA_WRITE_IDLE;
    if (result == 2 || result == EP5_WHEEL_SAVED) {
        change_revision(ui);
        (void)ep5_camera_menu_capture(ui,mount,&ui->confirmed);
    }
    return result;
}

/* Slot paths use fixed bank and slot ordinals. A changed look in an existing
 * slot is independently rejected by the identity inside the EP5W record. */
static void wheel_path(char path[24], unsigned bank, unsigned slot)
{
    const char *root="EP5LUT/";
    while (*root) *path++=*root++;
    if (bank>1) {
        *path++='B'; *path++='0'; *path++=(char)('0'+bank); *path++='/';
    }
    *path++='W'; *path++=(char)('0'+slot/10); *path++=(char)('0'+slot%10);
    const char *ext=".EP5";
    do { *path++=*ext; } while (*ext++);
}

int ep5_camera_wheel_take(struct ep5_camera_menu *ui, uint32_t mount, struct ep5_camera_wheel_job *job)
{
    if (!valid_mount(ui,mount) || !job || !ui->store.load || ui->wheel_inflight || ui->finishing_write ||
        (!ui->restore_next && ui->wheel_write!=EP5_CAMERA_WRITE_QUEUED)) return 0;
    unsigned bank=ui->browser.selected, slot=ui->looks.cursor+1u;
    job->write=ui->wheel_write==EP5_CAMERA_WRITE_QUEUED;
    if (job->write) {
        if (!ep5_wheel_encode(&ui->wheel.draft,job->record,sizeof job->record)) {
            ui->wheel_write=EP5_CAMERA_WRITE_FAILED;
            ui->wheel.active=1;
            return 0;
        }
    } else {
        while (ui->restore_next<=EP5_LUT_MENU_SLOTS &&
               !ui->looks.slots[ui->restore_next-1].configured) ++ui->restore_next;
        if (ui->restore_next>EP5_LUT_MENU_SLOTS) {
            ui->restore_next=0;
            return 0;
        }
        slot=ui->restore_next;
    }
    job->store=ui->store;
    job->mount=mount;
    job->bank=(uint8_t)bank;
    job->slot=(uint8_t)slot;
    if (++ui->wheel_ticket==0) ++ui->wheel_ticket;
    job->ticket=ui->wheel_ticket;
    ui->wheel_inflight=1;
    wheel_path(job->path,bank,slot);
    return 1;
}

int ep5_camera_wheel_execute(struct ep5_camera_wheel_job *job)
{
    if (!job || !job->ticket) return -1;
    if (job->write) return job->store.replace(job->store.ctx,job->mount,job->path,job->record);
    return job->store.load(job->store.ctx,job->mount,job->path,job->record);
}

int ep5_camera_wheel_finish(struct ep5_camera_menu *ui, uint32_t mount,
                            const struct ep5_camera_wheel_job *job, int result)
{
    if (valid_mount(ui,mount) && job && job->mount==mount && job->write &&
        ui->finishing_write && job->ticket==ui->finishing_write) {
        ui->finishing_write=0;
        return EP5_LUT_JOB_CANCELLED; /* publication belongs to the previous foreground */
    }
    if (!valid_mount(ui,mount) || !job || job->mount!=mount || !ui->wheel_inflight ||
        job->ticket!=ui->wheel_ticket || job->bank!=ui->browser.selected ||
        (job->write ? ui->wheel_write!=EP5_CAMERA_WRITE_QUEUED || job->slot!=ui->looks.cursor+1
                    : !ui->restore_next || job->slot!=ui->restore_next)) return EP5_LUT_JOB_CANCELLED;
    ui->wheel_inflight=0;
    unsigned i=job->slot-1;
    struct ep5_wheel_edit *saved=&ui->saved[job->bank-1][i];
    if (!job->write) {
        const struct ep5_lut_menu_slot *slot=&ui->looks.slots[i];
        struct ep5_wheel_edit edit;
        saved->number=0;
        if (result==1 && ep5_wheel_decode(job->record,sizeof job->record,&edit)) {
            if (edit.picture_mode==slot->picture_mode && edit.variant==slot->variant &&
                edit.number==slot->number && edit.look_crc==slot->look_crc)
                ep5_wheel_copy(saved,&edit);
        } else if (result!=0) {
            ui->unreadable_edits|=(uint16_t)(1u<<i);
        }
        ++ui->restore_next;
        return EP5_LUT_JOB_BUSY;
    }
    if (result!=1) {
        ui->wheel_write=EP5_CAMERA_WRITE_FAILED;
        ui->wheel.active=1; /* retain draft for retry or MENU to discard */
        return EP5_LUT_JOB_ERROR;
    }
    ep5_wheel_copy(saved,&ui->wheel.draft);
    ui->wheel_write=EP5_CAMERA_WRITE_IDLE;
    ui->unreadable_edits&=(uint16_t)~(1u<<i);
    change_revision(ui);
    (void)ep5_camera_menu_capture(ui,mount,&ui->confirmed);
    return EP5_CAMERA_SAVE_COMPLETE;
}

int ep5_camera_menu_step(struct ep5_camera_menu *ui, uint32_t mount)
{
    if (!ui) return EP5_LUT_JOB_ERROR;
    if (!valid_mount(ui,mount)) {
        if (mount) return EP5_LUT_JOB_CANCELLED;
        eject(ui);
    }
    if (ui->wheel_inflight || ui->finishing_write) return EP5_LUT_JOB_BUSY;
    if (ui->wheel_write==EP5_CAMERA_WRITE_QUEUED || ui->restore_next) {
        struct ep5_camera_wheel_job job;
        if (ep5_camera_wheel_take(ui,mount,&job))
            return ep5_camera_wheel_finish(ui,mount,&job,ep5_camera_wheel_execute(&job));
        return ui->wheel_write==EP5_CAMERA_WRITE_FAILED ? EP5_LUT_JOB_ERROR : EP5_LUT_JOB_INDEX_READY;
    }
    /* An obsolete open index is closed by its original worker and view. */
    if (ui->browser.job.status==EP5_LUT_JOB_BUSY || ui->browser.job.file) {
        int status=ep5_lut_bank_step(&ui->browser,&ui->looks);
        if (status==EP5_LUT_JOB_INDEX_READY && ui->page==EP5_CAMERA_LOOKS && !ui->pending &&
            ui->store.load && ui->looks.state==EP5_LUT_MENU_READY) {
            ui->restore_next=1;
            ui->unreadable_edits=0;
            return EP5_LUT_JOB_BUSY;
        }
        return ui->pending ? EP5_LUT_JOB_BUSY : status;
    }
    if (ui->pending) {
        unsigned bank=ui->pending;
        ui->pending=0;
        if (!ep5_lut_bank_select(&ui->browser,&ui->looks,bank))
            return EP5_LUT_JOB_ERROR;
        return EP5_LUT_JOB_BUSY;
    }
    return ui->browser.job.status;
}

int ep5_camera_menu_capture(const struct ep5_camera_menu *ui, uint32_t mount, struct ep5_camera_choice *out)
{
    if (!out) return 0;
    if (valid_mount(ui,mount) && ui->page==EP5_CAMERA_CLOSED && ui->confirmed.mount==mount) {
        ep5_copy_bytes(out, &ui->confirmed, sizeof *out);
        return 1;
    }
    ep5_zero_bytes(out, sizeof *out);
    if (!valid_mount(ui,mount) || ui->pending || ui->restore_next || !ui->browser.selected ||
        !ep5_lut_menu_capture(&ui->looks,&out->look)) return 0;
    out->bank=(uint8_t)ui->browser.selected;
    out->mount=mount;
    out->revision=ui->revision;
    const struct ep5_wheel_edit *edit=&ui->saved[out->bank-1][ui->looks.applied-1];
    if (edit->number==out->look.number && edit->number && edit->picture_mode==out->look.picture_mode &&
        edit->variant==out->look.variant && edit->look_crc==out->look.look_crc) {
        out->has_wheel=1;
        for (unsigned a=0;a<3;++a)
            for (unsigned i=0;i<EP5_WHEEL_SECTORS;++i)
                out->wheel.axis[a][i]=edit->values.axis[a][i];
    }
    return 1;
}

int ep5_camera_menu_choice_current(const struct ep5_camera_menu *ui, uint32_t mount,
                                   const struct ep5_camera_choice *choice)
{
    struct ep5_camera_choice active;
    if (!choice || !ep5_camera_menu_capture(ui,mount,&active)) return 0;
    return choice->mount==active.mount && choice->revision==active.revision && choice->bank==active.bank &&
           active.look.picture_mode==choice->look.picture_mode && active.look.variant==choice->look.variant &&
           active.look.number==choice->look.number && active.look.look_crc==choice->look.look_crc &&
           active.look.amount_q8==choice->look.amount_q8;
}

static void draw_label(const struct ep5_wheel_surface *s, unsigned x, unsigned y,const wchar_t *str)
{
    uint16_t label[28];
    unsigned i=0;
    while (i+1<sizeof label/sizeof label[0] && str[i]) {
        label[i]=(uint16_t)str[i];
        ++i;
    }
    label[i]=0;
    s->text(s->ctx,x,y,label,0xf2f5f6);
}

int ep5_camera_menu_draw(const struct ep5_camera_menu *ui, uint32_t mount,
                         const struct ep5_wheel_surface *s,
                         const struct ep5_camera_look_status *status)
{
    if (!valid_mount(ui,mount) || ui->page==EP5_CAMERA_CLOSED || !s || !s->fill || !s->text ||
        s->columns<42 || s->rows<13) return 0;
    if (ui->wheel.active) {
        int drawn=ep5_wheel_draw(&ui->wheel,&ui->looks,mount,s);
        if (drawn) {
            s->fill(s->ctx,0,11,42,1,0x15202a);
            if (ui->wheel_write==EP5_CAMERA_WRITE_FAILED) draw_label(s,1,11,L"写卡失败  选保存重试");
            else draw_label(s,1,11,L"主拨盘选色区  副拨盘调值");
        }
        return drawn;
    }
    s->fill(s->ctx,0,0,42,13,0x15202a);
    uint16_t ordinal[]={'1','/','3',0};
    ordinal[0]=(uint16_t)('0'+ui->group_focus);
    s->text(s->ctx,36,0,ordinal,0xb4c2cc);
    if (ui->page==EP5_CAMERA_GROUPS) {
        draw_label(s,1,0,L"胶片分组");
        for (unsigned g=1;g<=EP5_LUT_BANK_COUNT;++g) {
            unsigned y=1+g*2;
            if (g==ui->group_focus) s->fill(s->ctx,1,y,39,1,0x355a70);
            draw_label(s,3,y,L"胶片组");
            uint16_t number[]={(uint16_t)('0'+g),0};
            s->text(s->ctx,11,y,number,0xf2f5f6);
        }
        draw_label(s,1,11,L"主拨盘或上下选组  OK 打开");
        draw_label(s,1,12,L"MENU 返回拍摄");
        return 1;
    }
    draw_label(s,1,0,L"胶片风格");
    if (ui->wheel_write==EP5_CAMERA_WRITE_QUEUED || ui->restore_next) {
        if (ui->restore_next) draw_label(s,2,4,L"正在读取色轮调整");
        else draw_label(s,2,4,L"正在保存色轮调整");
        if (!ui->wheel_inflight || ui->restore_next) draw_label(s,1,12,L"MENU 取消");
        return 1;
    }
    struct ep5_look_page page;
    if (ui->pending || !ep5_lut_menu_page(&ui->looks,&page) || page.state==EP5_LUT_MENU_LOADING) {
        draw_label(s,2,4,L"正在读取色表索引");
    } else if (page.state==EP5_LUT_MENU_ERROR) {
        draw_label(s,2,4,L"读取失败   OK 重试");
    } else {
        for (unsigned i=0;i<page.count;++i) {
            struct ep5_look_page_row *row=&page.rows[i];
            unsigned y=2+2*i;
            if (row->focused) s->fill(s->ctx,1,y,39,1,0x355a70);
            if (row->confirmed) draw_label(s,2,y,L"*");
            row->name[6]=0;
            s->text(s->ctx,5,y,row->name,0xf2f5f6);
            unsigned p=row->percent;
            uint16_t percent[5]; unsigned n=0;
            if (p==100) percent[n++]='1';
            if (p>=10) percent[n++]=(uint16_t)('0'+p/10%10);
            percent[n++]=(uint16_t)('0'+p%10);
            percent[n++]='%'; percent[n]=0;
            s->text(s->ctx,32,y,percent,0xb4c2cc);
        }
        if (ui->unreadable_edits & (1u<<ui->looks.cursor))
            draw_label(s,1,10,L"色轮读取失败  使用基础风格");
        else draw_label(s,1,10,L"主拨盘选风格  副拨盘调强度");
        const wchar_t *hint = L"OK 选用   再按 OK 调色";
        if (ui->looks.applied == ui->looks.cursor + 1u &&
            ui->looks.slots[ui->looks.cursor].amount_q8 == ui->looks.amount_q8) {
            if (!ui->looks.amount_q8) hint = L"胶片效果关闭";
            else if (status && ep5_camera_menu_choice_current(ui,mount,status->choice)) {
                if (status->preload == EP5_LUT_JOB_BUSY) hint = L"正在载入色表";
                else if (status->preload == EP5_LUT_JOB_ERROR ||
                         status->preload == EP5_LUT_JOB_CANCELLED ||
                         status->preload == EP5_LUT_JOB_STOCK) hint = L"色表不可用  使用原色";
                else if (status->preload == EP5_LUT_JOB_APPLY) hint = L"色表已就绪  OK 调色";
            }
        }
        draw_label(s,1,11,hint);
    }
    draw_label(s,1,12,L"MENU 返回分组");
    return 1;
}
