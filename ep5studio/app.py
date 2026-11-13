"""Offline E-P5 desktop look library. Tk widgets are accessed only on the UI thread."""
import io
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageOps, ImageTk

from .library import Library
from .preview import preview_rgb8
from .project import Binding, Project, SLOTS, load_project, save_project


BG, PANEL, INK, MUTED = "#f4f4ef", "#fdfdf9", "#203b34", "#596d64"
GREEN, LIGHT, LINE = "#20684e", "#e3eee6", "#bdcfc0"
ENC = {"unknown":"未声明", "srgb":"sRGB（显示）", "rec709":"Rec.709", "vlog":"V-Log / V-Gamut"}
FONT = "Microsoft YaHei UI"


def amount_q8(percent):
    return (max(0,min(100,int(round(percent)))) * 256 + 50) // 100


def export_available(bindings,looks):
    return bool(bindings) and all((b.look_id in looks and looks[b.look_id].directly_compatible)
                                  for b in bindings.values())


def sample_image():
    """Original synthetic still life: warm colour patches, foliage, grey and shadows."""
    w,h = 640,440
    y,x = np.mgrid[:h,:w]
    t = np.clip(.56*x/w + .44*y/h,0,1)[:,:,None]
    rgb = np.array([231,217,185])*(1-t) + np.array([144,167,135])*t
    floor = y > h*.66
    rgb[floor] = (np.array([181,135,99]) - (x[floor]/w)[:,None]*np.array([38,19,10]))
    im = Image.fromarray(np.uint8(rgb))
    d = ImageDraw.Draw(im)
    d.ellipse((99,313,492,355),fill="#886b56")
    d.rounded_rectangle((221,190,344,321),radius=24,fill="#496a61")
    d.rectangle((247,155,314,215),fill="#496a61")
    d.ellipse((247,146,314,166),fill="#638579")
    d.ellipse((252,150,309,162),fill="#334d45")
    for (end, leaves) in [((180,58),[(189,69,228,85),(169,77,196,95)]),
                          ((302,38),[(277,70,302,87),(302,42,337,62)]),
                          ((386,83),[(335,107,376,121),(367,79,409,97)])]:
        d.line([(280,155),end],fill="#4b6143",width=4)
        for bounds in leaves:
            d.ellipse(bounds,fill="#697c4d")
    d.ellipse((92,271,170,337),fill="#d48230")
    d.ellipse((142,283,216,349),fill="#e5a14a")
    d.ellipse((155,285,168,291),fill="#697347")
    d.rounded_rectangle((386,255,481,325),radius=14,fill="#dcc9ae")
    d.ellipse((385,247,482,267),fill="#ece2cb")
    d.ellipse((396,250,472,262),fill="#7e5b43")
    d.arc((467,260,505,306),270,90,fill="#d4bea1",width=7)
    for i,col in enumerate(("#383e3c","#808580","#d0cfbf","#853837","#dd9a3e","#638350","#477d89","#626c91")):
        x0=88+i*58
        d.rectangle((x0,383,x0+54,405),fill=col)
    return im


class NeedsProfile(ValueError):
    pass


def load_preview(path, assume_srgb=False):
    """Load a bounded local display copy; never write the source image."""
    with Image.open(path, formats=("JPEG","PNG")) as source:
        if source.width * source.height > 70_000_000:
            raise ValueError("照片超过 7000 万像素，请使用较小的预览副本")
        exif = source.getexif()
        exif_ifd = exif.get_ifd(34665)
        space = exif_ifd.get(40961,exif.get(40961))
        icc = source.info.get("icc_profile")
        interp = exif.get_ifd(40965).get(1,"") if 40965 in exif_ifd else ""
        if isinstance(interp,bytes):interp=interp.decode("ascii",errors="replace").rstrip("\0")
        if not icc and (space==2 or interp=="R03"):
            raise ValueError("照片标记为 Adobe RGB，但缺少可转换的 ICC；请先导出带配置的 sRGB 副本")
        if not icc and space != 1 and "srgb" not in source.info and not assume_srgb:
            raise NeedsProfile("照片没有可用的 sRGB 标记。")
        image = ImageOps.exif_transpose(source)
        image.thumbnail((1200,900),Image.Resampling.LANCZOS)
        if icc:
            try:
                converted = ImageCms.profileToProfile(image,ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                                        ImageCms.createProfile("sRGB"),outputMode="RGB")
            except (ImageCms.PyCMSError,ValueError,OSError) as exc:
                raise ValueError("无法转换照片的 ICC 配置；请先导出 sRGB 的 JPG/PNG") from exc
            return converted,"ICC → sRGB"
        return image.convert("RGB"),"按 sRGB 预览" if assume_srgb else "sRGB"


class Studio:
    def __init__(self, root, library=None, preview_image=None):
        self.root = root
        self.library = library if library is not None else Library()
        self.looks, self.bindings, self.current_id = {}, {}, None
        self.project_name, self.dirty = "我的 E-P5 风格",False
        self.source = sample_image()
        self.source_desc = "内置测试静物 · sRGB"
        self.result = None
        self.epoch = 0
        self._photos = []
        self._timer = None
        self._paint_timer = None
        self._poll_timer = None
        self._image_epoch = 0
        self._closed = threading.Event()
        self._jobs, self._results = queue.Queue(),queue.Queue()
        self._busy = False
        self._errors = []
        self.start_ready = False
        self.display_ready = False
        self._worker = threading.Thread(target=self._work,name="ep5-studio",daemon=True)
        self._worker.start()
        self._make_ui()
        self.root.protocol("WM_DELETE_WINDOW",self.close)
        self._poll_timer = root.after(25,self._poll)
        def initial():
            errors=[]
            try:self.library.seed_defaults()
            except (OSError,ValueError) as exc:errors.append("内置风格："+str(exc))
            return self.library.list_looks(),errors+list(self.library.errors)
        def loaded(data):
            self._refresh(*data)
            self.start_ready = True
            if preview_image:
                self.open_image(preview_image)
        self._post(initial,loaded,title="载入风格库")

    def _work(self):
        while not self._closed.is_set():
            task = self._jobs.get()
            if task is None:
                return
            fn,ok,bad,token = task
            if token is not None and token != self.epoch:
                continue
            try:
                value = fn()
            except Exception as exc:
                self._results.put((bad,exc,token))
            else:
                self._results.put((ok,value,token))

    def _post(self,fn,ok,bad=None,token=None,title=None):
        if title: self.status.set(title+"…")
        self._jobs.put((fn,ok,bad or self._error,token))

    def _poll(self):
        if self._closed.is_set():
            return
        try:
            while True:
                cb,value,token = self._results.get_nowait()
                if token is None or token == self.epoch:
                    try: cb(value)
                    except Exception as exc: self._error(exc)
        except queue.Empty:
            pass
        self._poll_timer = self.root.after(35,self._poll)

    def _error(self,exc):
        self._busy = False
        self._errors.append(str(exc))
        self.status.set("操作未完成："+str(exc))
        self._buttons()

    def _styles(self):
        style=ttk.Style(self.root)
        style.theme_use("clam")
        self.root.option_add("*Font",(FONT,10))
        style.configure(".",font=(FONT,10),background=PANEL,foreground=INK)
        style.configure("TFrame",background=PANEL)
        style.configure("TLabel",background=PANEL,foreground=INK)
        style.configure("TButton",font=(FONT,10),padding=(8,5),background=PANEL,bordercolor=LINE)
        style.map("TButton",background=[("active",LIGHT)])
        style.configure("Accent.TButton",background=GREEN,foreground="white",bordercolor=GREEN)
        style.map("Accent.TButton",background=[("disabled","#d7dfd7"),("active","#17523d")],
                  foreground=[("disabled","#607067"),("!disabled","white")])
        style.configure("Treeview",rowheight=31,background=PANEL,fieldbackground=PANEL,
                        borderwidth=0,font=(FONT,10),foreground=INK)
        style.map("Treeview",background=[("selected",LIGHT)],foreground=[("selected",INK)])
        style.configure("Treeview.Heading",font=(FONT,9),background=BG,foreground=MUTED)
        style.configure("TCombobox",padding=(3,3),fieldbackground="white")

    def _make_ui(self):
        self.root.title("E-P5 LUT Studio")
        self.root.configure(bg=BG)
        w=max(920,min(1380,self.root.winfo_screenwidth()-36))
        h=max(640,min(840,self.root.winfo_screenheight()-78))
        self.root.geometry(f"{w}x{h}"); self.root.minsize(920,640)
        self._styles()
        head=tk.Frame(self.root,bg=INK,padx=18,pady=10); head.pack(fill="x")
        tk.Label(head,text="E-P5  /  LUT Studio",font=(FONT,17,"bold"),fg="#fffcf2",bg=INK).pack(side="left")
        tk.Label(head,text="胶片风格工作台",font=(FONT,10),fg="#b4cdbd",bg=INK,padx=12).pack(side="left")
        ttk.Button(head,text="保存项目",command=self.save).pack(side="right",padx=(5,0))
        ttk.Button(head,text="打开项目",command=self.open_project).pack(side="right")
        banner=tk.Frame(self.root,bg=LIGHT,padx=18,pady=5); banner.pack(fill="x")
        tk.Label(banner,text="●  离线桌面工具",fg=GREEN,bg=LIGHT,font=(FONT,10,"bold")).pack(side="left")
        tk.Label(banner,text="机内 SD 运行时尚未发布；此工具不能生成刷机固件。",fg=INK,bg=LIGHT,padx=12).pack(side="left")
        work=tk.PanedWindow(self.root,orient="horizontal",bg=BG,sashwidth=6,showhandle=False,bd=0)
        work.pack(fill="both",expand=True,padx=8,pady=8)
        left=ttk.Frame(work,padding=(12,10)); middle=ttk.Frame(work,padding=(13,10)); right=ttk.Frame(work,padding=(12,10))
        work.add(left,minsize=186,width=235,stretch="never"); work.add(middle,minsize=320,stretch="always")
        work.add(right,minsize=230,width=275,stretch="never")
        self._heading(left,"01  /  LIBRARY","风格库")
        self.import_btn=ttk.Button(left,text="＋  导入 .cube…",style="Accent.TButton",command=self.import_files)
        self.import_btn.pack(fill="x",pady=(4,8))
        self.tree=ttk.Treeview(left,show="tree",selectmode="browse",height=5)
        self.tree.column("#0",minwidth=90,width=150,stretch=True)
        self.tree.pack(fill="both",expand=True)
        self.tree.bind("<<TreeviewSelect>>",self._selected)
        self.look_meta=tk.StringVar(value="先选择一个风格")
        ttk.Label(left,textvariable=self.look_meta,foreground=MUTED,wraplength=180).pack(anchor="w",pady=(7,6))
        ttk.Separator(left).pack(fill="x")
        ttk.Label(left,text="LUT 颜色声明",font=(FONT,10,"bold")).pack(anchor="w",pady=(9,4))
        self.from_enc,self.to_enc=tk.StringVar(),tk.StringVar()
        for title,var in (("输入",self.from_enc),("输出",self.to_enc)):
            row=ttk.Frame(left);row.pack(fill="x",pady=2)
            ttk.Label(row,text=title,width=4).pack(side="left")
            ttk.Combobox(row,textvariable=var,values=list(ENC.values()),state="readonly",width=10).pack(fill="x",expand=True)
        self.enc_btn=ttk.Button(left,text="保存颜色声明",command=self.apply_declaration);self.enc_btn.pack(fill="x",pady=(4,1))
        ttk.Label(left,text="按 LUT 作者说明填写；V-Log 专用 LUT 不能直接套在 sRGB 照片上。",
                  foreground=MUTED,font=(FONT,9),wraplength=178,justify="left").pack(anchor="w",pady=(4,0))
        self._heading(middle,"02  /  PREVIEW","照片预览")
        actions=ttk.Frame(middle);actions.pack(fill="x",pady=(2,7))
        ttk.Button(actions,text="打开照片…",command=self.choose_image).pack(side="left")
        ttk.Button(actions,text="测试静物",command=self.reset_sample).pack(side="left",padx=(5,0))
        self.source_label=tk.StringVar(value=self.source_desc)
        ttk.Label(middle,textvariable=self.source_label,foreground=MUTED).pack(anchor="w",pady=(0,6))
        cards=ttk.Frame(middle);cards.pack(fill="both",expand=True)
        cards.columnconfigure((0,1),weight=1,uniform="p");cards.rowconfigure(1,weight=1)
        self.canvases=[]
        for i,caption in enumerate(("原图","风格预览 · 17³")):
            ttk.Label(cards,text=caption,font=(FONT,10,"bold")).grid(row=0,column=i,sticky="w",pady=(0,4))
            c=tk.Canvas(cards,bg="#e9e9e1",highlightthickness=0,width=80,height=120)
            c.grid(row=1,column=i,sticky="nsew",padx=(0,3) if not i else (3,0))
            c.bind("<Configure>",self._defer_paint);self.canvases.append(c)
        strength=ttk.Frame(middle);strength.pack(fill="x",pady=(10,4))
        ttk.Label(strength,text="风格强度",font=(FONT,10,"bold")).pack(side="left")
        self.amount=tk.DoubleVar(value=100); self.amount_label=tk.StringVar(value="100%")
        ttk.Label(strength,textvariable=self.amount_label,foreground=GREEN).pack(side="right")
        self.slider=ttk.Scale(middle,from_=0,to=100,variable=self.amount,command=self._strength); self.slider.pack(fill="x")
        self.render_note=tk.StringVar(value="选择风格查看效果。")
        ttk.Label(middle,textvariable=self.render_note,foreground=MUTED,font=(FONT,9),wraplength=340).pack(anchor="w",pady=(7,0))
        self._heading(right,"03  /  PROJECT","ART 位置")
        self.slot=tk.StringVar(value=SLOTS["pin-hole-i"]["label"])
        ttk.Combobox(right,textvariable=self.slot,state="readonly",values=[s["label"] for s in SLOTS.values()]).pack(fill="x",pady=(4,6))
        ttk.Label(right,text="菜单短名（最多 6 字）",foreground=MUTED).pack(anchor="w")
        self.short=tk.StringVar();ttk.Entry(right,textvariable=self.short).pack(fill="x",pady=(2,6))
        self.bind_btn=ttk.Button(right,text="将当前风格分配到此位置",command=self.bind_look);self.bind_btn.pack(fill="x")
        self.binding_tree=ttk.Treeview(right,columns=("binding",),show="tree headings",height=2,selectmode="browse")
        self.binding_tree.heading("#0",text="拟用 ART");self.binding_tree.heading("binding",text="短名 / 强度")
        self.binding_tree.column("#0",width=90,minwidth=65);self.binding_tree.column("binding",width=100,minwidth=75)
        self.binding_tree.pack(fill="both",expand=True,pady=(8,3))
        self.binding_tree.bind("<<TreeviewSelect>>",self.select_binding)
        ttk.Button(right,text="移除选中分配",command=self.unbind).pack(anchor="e")
        ttk.Separator(right).pack(fill="x",pady=8)
        self.project_label=tk.StringVar(value=self.project_name)
        ttk.Label(right,textvariable=self.project_label,foreground=INK,font=(FONT,10,"bold"),wraplength=225).pack(anchor="w")
        self.export_btn=ttk.Button(right,text="导出开发用风格包…",style="Accent.TButton",command=self.export)
        self.export_btn.pack(fill="x",pady=(5,4))
        ttk.Button(right,text="生成刷机固件 · 尚不可用",state="disabled").pack(fill="x")
        self.status=tk.StringVar(value="准备风格库…")
        # Reserve the status row *before* the stretchable workspace. Packing
        # it last allowed the panes to consume every pixel at minimum height.
        foot=tk.Frame(self.root,bg=INK,padx=12,pady=4);foot.pack(side="bottom",fill="x",before=work)
        tk.Label(foot,textvariable=self.status,bg=INK,fg="#e1eee4",anchor="w",font=(FONT,9)).pack(side="left",fill="x",expand=True)
        ttk.Button(foot,text="记录",command=self.show_errors).pack(side="right")
        self._buttons()

    def _heading(self,parent,index,title):
        ttk.Label(parent,text=index,font=("Segoe UI",8,"bold"),foreground=GREEN).pack(anchor="w")
        ttk.Label(parent,text=title,font=(FONT,15,"bold")).pack(anchor="w",pady=(1,5))

    def _buttons(self):
        self.import_btn.state(["disabled"] if self._busy else ["!disabled"])
        self.enc_btn.state(["!disabled"] if self.current_id and not self._busy else ["disabled"])
        self.bind_btn.state(["!disabled"] if self.current_id else ["disabled"])
        valid=export_available(self.bindings,self.looks)
        self.export_btn.state(["!disabled"] if valid and not self._busy else ["disabled"])

    def _refresh(self,looks,errors,select=None):
        self._errors.extend(errors)
        self.looks={v.id:v for v in looks}
        self.tree.delete(*self.tree.get_children())
        for v in looks:
            self.tree.insert("","end",iid=v.id,text=f"{v.title}  ·  {v.side}³")
        key=select if select in self.looks else self.current_id
        if key not in self.looks:
            key=next((v.id for v in looks if v.source_filename=="Gold200.cube"),
                     next((v.id for v in looks if v.source_filename=="WarmNegative.cube"),next(iter(self.looks),None)))
        self.current_id=None
        if key: self._select(key)
        else:
            self.short.set("");self.look_meta.set("尚无可用风格");self._render()
        self.status.set(f"风格库 · {len(looks)} 款"+(f"  /  {len(errors)} 条异常，详见记录" if errors else ""))
        self._buttons()

    def _select(self,key):
        if key not in self.looks: return
        if self.tree.selection()!=(key,): self.tree.selection_set(key);self.tree.see(key)
        if key==self.current_id: return
        v=self.looks[key]; self.current_id=key
        self.look_meta.set(f"{v.title}\n原表 {v.side}³   →   预览 17³")
        self.from_enc.set(ENC[v.input_encoding]);self.to_enc.set(ENC[v.output_encoding])
        self.short.set("".join(c for c in v.title if ord(c)<=65535)[:6].strip())
        self._buttons();self._render()

    def _selected(self,_event=None):
        keys=self.tree.selection()
        if keys: self._select(keys[0])

    def import_files(self):
        paths=filedialog.askopenfilenames(parent=self.root,title="导入 LUT",filetypes=[("三维 LUT","*.cube")])
        if not paths:return
        self._busy=True;self._buttons()
        old=set(self.looks)
        def work():
            ids,errors=[],[]
            for name in paths:
                try: ids.append(self.library.import_file(name).id)
                except Exception as exc: errors.append(f"{Path(name).name}：{exc}")
            looks=self.library.list_looks()
            return ids,looks,errors+list(self.library.errors)
        def done(data):
            ids,looks,errors=data; self._busy=False
            self._refresh(looks,errors,ids[-1] if ids else None)
            added=len(set(ids)-old)
            self.status.set(f"导入 {added} 款 · 已有或重复 {len(ids)-added} 款"+(f" · {len(errors)} 条异常，详见记录" if errors else ""))
        self._post(work,done,title="正在导入 LUT")

    def apply_declaration(self):
        key=self.current_id
        if not key:return
        rev={v:k for k,v in ENC.items()}
        a,b=rev[self.from_enc.get()],rev[self.to_enc.get()]
        self._busy=True;self._buttons()
        def done(v):
            self._busy=False;self.looks[key]=v
            self._buttons();self._render();self.status.set("颜色声明已保存")
        self._post(lambda:self.library.set_encodings(key,a,b),done,title="保存颜色声明")

    def choose_image(self):
        p=filedialog.askopenfilename(parent=self.root,title="选择本地照片",filetypes=[("JPEG / PNG","*.jpg *.jpeg *.png")])
        if p:self.open_image(p)

    def open_image(self,p,assume=False):
        self._image_epoch+=1;generation=self._image_epoch
        def done(value):
            if generation!=self._image_epoch:return
            self.source,note=value;self.source_desc=Path(p).name+" · "+note
            self.source_label.set(self.source_desc);self._render();self.status.set("已载入本地照片")
        def bad(exc):
            if generation!=self._image_epoch:return
            if isinstance(exc,NeedsProfile):
                if messagebox.askyesno("照片颜色空间",str(exc)+"\n按 sRGB 解释这张照片，仅用于预览？",parent=self.root):
                    self.open_image(p,True)
                else:self.status.set("已保留原预览")
            else:self._error(exc)
        self._post(lambda:load_preview(p,assume),done,bad,title="读取照片")

    def reset_sample(self):
        self._image_epoch+=1;self.source=sample_image();self.source_desc="内置测试静物 · sRGB"
        self.source_label.set(self.source_desc);self._render()

    def _strength(self,value):
        self.amount_label.set(f"{round(float(value))}%");self._render()

    def _render(self):
        self.epoch+=1;epoch=self.epoch
        self.display_ready=False
        if self._timer:self.root.after_cancel(self._timer);self._timer=None
        self.result=None;self._paint()
        look=self.looks.get(self.current_id)
        if not look or not look.directly_compatible:
            self.render_note.set("请选择风格。" if not look else "预览需要确认 sRGB 输入和 sRGB 输出；请查看作者说明。")
            self.display_ready=True;return
        self.render_note.set(f"{look.title} · 计算 17³ 桌面预览…")
        q=amount_q8(self.amount.get());source=self.source
        def run():
            self._timer=None
            def work():return Image.fromarray(preview_rgb8(np.asarray(source),self.library.table(look.id),q))
            def done(value):
                self.result=value;self.display_ready=True;self._paint()
                self.render_note.set(f"{look.title} · 17³ 软件预览，未模拟机内 ISP")
            self._post(work,done,token=epoch)
        self._timer=self.root.after(65,run)

    def _defer_paint(self,_event=None):
        if self._paint_timer:self.root.after_cancel(self._paint_timer)
        self._paint_timer=self.root.after(45,self._paint)

    def _paint(self):
        if self._paint_timer:self.root.after_cancel(self._paint_timer);self._paint_timer=None
        self._photos=[]
        for canvas,im in zip(self.canvases,(self.source,self.result)):
            w=max(1,canvas.winfo_width());h=max(1,canvas.winfo_height())
            canvas.delete("all")
            if im is None:
                canvas.create_text(w/2,h/2,text="风格预览",fill=MUTED,font=(FONT,10));continue
            scale=min(w/im.width,h/im.height)
            size=(max(1,round(im.width*scale)),max(1,round(im.height*scale)))
            display=im.resize(size,Image.Resampling.LANCZOS)
            pic=ImageTk.PhotoImage(display,master=self.root);self._photos.append(pic)
            canvas.create_image(w//2,h//2,image=pic)

    def bind_look(self):
        if not self.current_id:return
        try:
            slot=next(k for k,s in SLOTS.items() if s["label"]==self.slot.get())
            b=Binding(slot,self.current_id,self.short.get().strip(),amount_q8(self.amount.get()))
            self.bindings[slot]=b;self._bindings_changed();self.status.set("已分配至 "+self.slot.get())
        except ValueError as exc:self._error(exc)

    def _bindings_changed(self,dirty=True):
        if dirty:self.dirty=True
        self.binding_tree.delete(*self.binding_tree.get_children())
        for key in SLOTS:
            if key not in self.bindings:continue
            b=self.bindings[key]
            self.binding_tree.insert("","end",iid=key,text=SLOTS[key]["label"],values=(f"{b.label} · {round(b.amount_q8*100/256)}%",))
        self.project_label.set(self.project_name+("  ·  未保存" if self.dirty else ""))
        self._buttons()

    def select_binding(self,_event=None):
        selected=self.binding_tree.selection()
        if not selected:return
        b=self.bindings.get(selected[0])
        if b is None:return
        self.slot.set(SLOTS[b.slot_id]["label"])
        if b.look_id not in self.looks:
            self.status.set("该分配的原始 LUT 不在此风格库，请重新导入。");return
        self._select(b.look_id);self.short.set(b.label)
        self.amount.set(round(b.amount_q8*100/256));self._strength(self.amount.get())

    def unbind(self):
        for k in self.binding_tree.selection():self.bindings.pop(k,None)
        self._bindings_changed()

    def project(self):
        return Project(self.project_name,tuple(self.bindings[k] for k in SLOTS if k in self.bindings))

    def save(self):
        path=filedialog.asksaveasfilename(parent=self.root,title="保存风格项目",defaultextension=".json",
                                          filetypes=[("风格项目","*.json")],initialfile=self.project_name+".json")
        if not path:return
        try:
            if Path(path).suffix.lower()!=".json":raise ValueError("项目文件扩展名必须为 .json")
            project=Project(Path(path).stem,self.project().bindings);save_project(project,path)
            self.project_name=project.name;self.dirty=False;self._bindings_changed(False);self.status.set("已保存项目："+Path(path).name)
        except (OSError,ValueError) as exc:self._error(exc)

    def open_project(self):
        path=filedialog.askopenfilename(parent=self.root,title="打开风格项目",filetypes=[("风格项目","*.json")])
        if not path:return
        if self.dirty and not messagebox.askyesno("未保存的项目","放弃未保存的分配并打开另一个项目？",parent=self.root):return
        try:
            p=load_project(path);self.project_name=p.name;self.bindings={b.slot_id:b for b in p.bindings}
            self.dirty=False;self._bindings_changed(False)
            missing=[b.label for b in p.bindings if b.look_id not in self.looks]
            self.status.set("请重新导入项目所用的 LUT："+", ".join(missing) if missing else "已打开："+p.name)
        except (OSError,ValueError) as exc:self._error(exc)

    def export(self):
        if self.export_btn.instate(["disabled"]):return
        path=filedialog.asksaveasfilename(parent=self.root,title="导出开发用风格包（不是固件）",
                                          defaultextension=".zip",filetypes=[("开发用风格包","*.zip")])
        if not path:return
        if Path(path).suffix.lower()!=".zip":return self._error(ValueError("开发用风格包扩展名必须为 .zip"))
        from .export import export_project
        p=self.project();self._busy=True;self._buttons()
        def done(_):
            self._busy=False;self._buttons();self.status.set("已导出开发用风格包，不能用于刷机："+Path(path).name)
        self._post(lambda:export_project(p,self.library,path),done,title="导出开发用风格包")

    def show_errors(self):
        messagebox.showinfo("操作记录","\n".join(self._errors[-12:]) or "没有报告错误。",parent=self.root)

    def close(self,force=False):
        if not force and self.dirty and not messagebox.askyesno("退出工作台","还有未保存的项目分配，确认退出？",parent=self.root):return
        self._closed.set();self._jobs.put(None)
        for token in (self._timer,self._paint_timer,self._poll_timer):
            if token:self.root.after_cancel(token)
        self._photos.clear();self.root.destroy()
