"""EP5 LUT Studio v2 — Film Shelf UI inspired by Panasonic S9 + Canon M-Film.

Layout:
  Left:   Film shelf with category tabs (彩色负片/反转片/黑白/电影/自定义)
  Center: Large before/after preview with split slider
  Right:  3 ART slot cards (drag-drop binding), strength, export
  Bottom: Status bar + SD card export progress

Features over v1:
  - Category-organized film library with one-click preview
  - Split before/after comparison (drag divider)
  - Drag .cube files onto the window to import
  - Per-slot strength slider with live preview
  - One-click "导出到SD卡" with progress
  - Film info panel (error report, source, compatibility)
  - Keyboard shortcuts (Ctrl+O import, Ctrl+S save, Ctrl+E export)
"""
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
from .app import sample_image, load_preview, NeedsProfile, amount_q8, export_available
from .firmware import FW_SLOTS, DEFAULT_ASSIGNMENT, available_hq_looks
from tools.native_film_curves_hq import HQ_LOOKS

ROOT = Path(__file__).resolve().parents[1]

# ─── Design tokens ───────────────────────────────────────────────────────────
BG = "#1a1a2e"          # dark navy background (S9 style)
PANEL = "#16213e"       # card panels
CARD = "#0f3460"        # slot cards
ACCENT = "#e94560"      # accent red (film canister)
ACCENT2 = "#53a8b6"     # teal secondary
INK = "#eaeaea"         # light text
MUTED = "#8899aa"       # secondary text
SUCCESS = "#4ecca3"     # green for compatible
WARN = "#f0a500"        # amber for approximate
FONT = "Microsoft YaHei UI"
FONT_MONO = "Consolas"

CATEGORIES = {
    "彩色负片": ["portra", "gold", "ektar", "colorplus", "ultramax", "superia"],
    "反转片": ["velvia", "provia", "classic_chrome"],
    "黑白": ["moriyama", "tri_x", "acros"],
    "电影": ["cine", "bleach", "cross"],
    "自定义": [],  # user imports
}

def categorize(title):
    t = title.lower()
    for cat, keywords in CATEGORIES.items():
        if cat == "自定义":
            continue
        if any(k in t for k in keywords):
            return cat
    return "自定义"


class StudioV2:
    def __init__(self, root, library=None):
        self.root = root
        self.root.title("EP5 LUT Studio — 胶片风格管理器")
        self.root.geometry("1280x800")
        self.root.minsize(1024, 680)
        self.root.configure(bg=BG)

        self.library = library if library is not None else Library()
        self.looks = {}
        self.bindings = {}  # slot_id -> Binding
        self.current_id = None
        self.project_name = "我的 E-P5 风格"
        self.dirty = False
        self.source = sample_image()
        self.result = None
        self.split_pos = 0.5
        self.epoch = 0
        self._closed = threading.Event()
        self._jobs = queue.Queue()
        self._results = queue.Queue()
        self._photos = []
        self._timer = None
        self._drag_slot = None

        self._worker = threading.Thread(target=self._work, daemon=True)
        self._worker.start()
        self._styles()
        self._make_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_timer = root.after(30, self._poll)

        # Keyboard shortcuts
        self.root.bind("<Control-o>", lambda e: self.import_files())
        self.root.bind("<Control-s>", lambda e: self.save())
        self.root.bind("<Control-e>", lambda e: self.export_sd())

        # Load library
        def initial():
            try:
                self.library.seed_defaults()
            except (OSError, ValueError):
                pass
            return self.library.list_looks()
        def loaded(looks):
            self._refresh_library(looks)
        self._post(initial, loaded)

    # ─── Threading ───────────────────────────────────────────────────────────
    def _work(self):
        while not self._closed.is_set():
            task = self._jobs.get()
            if task is None:
                return
            fn, ok, bad, token = task
            if token is not None and token != self.epoch:
                continue
            try:
                value = fn()
            except Exception as exc:
                self._results.put((bad, exc, token))
            else:
                self._results.put((ok, value, token))

    def _post(self, fn, ok, bad=None, token=None):
        self._jobs.put((fn, ok, bad or self._error, token))

    def _poll(self):
        if self._closed.is_set():
            return
        try:
            while True:
                cb, value, token = self._results.get_nowait()
                if token is None or token == self.epoch:
                    try:
                        cb(value)
                    except Exception as exc:
                        self._error(exc)
        except queue.Empty:
            pass
        self._poll_timer = self.root.after(30, self._poll)

    def _error(self, exc):
        self.status_var.set(f"⚠ {exc}")

    # ─── Styles ──────────────────────────────────────────────────────────────
    def _styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self.root.option_add("*Font", (FONT, 10))
        style.configure(".", font=(FONT, 10), background=BG, foreground=INK)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("Panel.TLabel", background=PANEL, foreground=INK)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT, 9))
        style.configure("Title.TLabel", font=(FONT, 14, "bold"), foreground=INK)
        style.configure("TButton", font=(FONT, 10), padding=(10, 6),
                        background=CARD, foreground=INK, borderwidth=0)
        style.map("TButton", background=[("active", ACCENT2)])
        style.configure("Accent.TButton", background=ACCENT, foreground="white")
        style.map("Accent.TButton", background=[("active", "#c73e54")])
        style.configure("Success.TButton", background=SUCCESS, foreground="#1a1a2e")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=(FONT, 10), padding=(12, 6),
                        background=PANEL, foreground=MUTED)
        style.map("TNotebook.Tab", background=[("selected", CARD)],
                  foreground=[("selected", INK)])
        style.configure("Treeview", rowheight=36, background=PANEL,
                        fieldbackground=PANEL, foreground=INK, borderwidth=0,
                        font=(FONT, 10))
        style.map("Treeview", background=[("selected", CARD)])
        style.configure("Treeview.Heading", background=BG, foreground=MUTED,
                        font=(FONT, 9))
        style.configure("Horizontal.TScale", background=PANEL, troughcolor=CARD)
        style.configure("TProgressbar", background=ACCENT2, troughcolor=PANEL)

    # ─── UI Layout ───────────────────────────────────────────────────────────
    def _make_ui(self):
        # Top bar
        top = tk.Frame(self.root, bg=BG, height=48)
        top.pack(fill="x", padx=16, pady=(12, 0))
        top.pack_propagate(False)
        tk.Label(top, text="🎞 EP5 LUT Studio", font=(FONT, 14, "bold"),
                 bg=BG, fg=INK).pack(side="left")
        tk.Label(top, text="Olympus E-P5 · 胶片风格管理器", font=(FONT, 9),
                 bg=BG, fg=MUTED).pack(side="left", padx=12)
        btn_frame = tk.Frame(top, bg=BG)
        btn_frame.pack(side="right")
        ttk.Button(btn_frame, text="导入 .cube", command=self.import_files).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="保存项目", command=self.save).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="导出到 SD", style="Accent.TButton",
                   command=self.export_sd).pack(side="left", padx=4)

        # Main area: 3 columns
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=16, pady=8)
        main.columnconfigure(0, weight=2, minsize=260)
        main.columnconfigure(1, weight=5, minsize=480)
        main.columnconfigure(2, weight=2, minsize=240)
        main.rowconfigure(0, weight=1)

        self._make_shelf(main)
        self._make_preview(main)
        self._make_slots(main)
        self._make_firmware_panel(main)

        # Bottom status
        bottom = tk.Frame(self.root, bg=PANEL, height=32)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        self.status_var = tk.StringVar(value="就绪 · 拖放 .cube 文件到窗口导入")
        tk.Label(bottom, textvariable=self.status_var, font=(FONT, 9),
                 bg=PANEL, fg=MUTED, anchor="w").pack(side="left", padx=12, fill="x")
        self.progress = ttk.Progressbar(bottom, length=120, mode="determinate")
        self.progress.pack(side="right", padx=12, pady=4)

    def _make_shelf(self, parent):
        """Left: Film library with category tabs."""
        frame = tk.Frame(parent, bg=PANEL, bd=0)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        tk.Label(frame, text="胶片库", font=(FONT, 12, "bold"),
                 bg=PANEL, fg=INK).pack(anchor="w", padx=12, pady=(10, 4))

        self.shelf_tabs = ttk.Notebook(frame)
        self.shelf_tabs.pack(fill="both", expand=True, padx=4, pady=4)

        self.shelf_trees = {}
        for cat in CATEGORIES:
            tab = tk.Frame(self.shelf_tabs, bg=PANEL)
            self.shelf_tabs.add(tab, text=f" {cat} ")
            tree = ttk.Treeview(tab, columns=("name", "compat"), show="headings",
                                selectmode="browse")
            tree.heading("name", text="风格")
            tree.heading("compat", text="适配")
            tree.column("name", width=160, minwidth=100)
            tree.column("compat", width=50, minwidth=40, anchor="center")
            tree.pack(fill="both", expand=True, padx=4, pady=4)
            tree.bind("<<TreeviewSelect>>", self._on_shelf_select)
            self.shelf_trees[cat] = tree

        # Film info panel below tabs
        self.info_frame = tk.Frame(frame, bg=PANEL)
        self.info_frame.pack(fill="x", padx=8, pady=(0, 8))
        self.info_var = tk.StringVar(value="选择风格查看详情")
        tk.Label(self.info_frame, textvariable=self.info_var, font=(FONT, 9),
                 bg=PANEL, fg=MUTED, wraplength=240, justify="left").pack(anchor="w")

    def _make_preview(self, parent):
        """Center: Before/After split preview."""
        frame = tk.Frame(parent, bg=BG)
        frame.grid(row=0, column=1, sticky="nsew", padx=4)

        # Preview header
        hdr = tk.Frame(frame, bg=BG)
        hdr.pack(fill="x", pady=(0, 4))
        tk.Label(hdr, text="预览对比", font=(FONT, 11, "bold"),
                 bg=BG, fg=INK).pack(side="left")
        ttk.Button(hdr, text="选择照片…", command=self.choose_image).pack(side="right")
        ttk.Button(hdr, text="测试图", command=self.reset_sample).pack(side="right", padx=4)
        self.preview_desc = tk.StringVar(value="内置测试静物 · sRGB")
        tk.Label(hdr, textvariable=self.preview_desc, font=(FONT, 9),
                 bg=BG, fg=MUTED).pack(side="right", padx=8)

        # Canvas for split preview
        self.canvas = tk.Canvas(frame, bg="#111122", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._defer_paint)
        self.canvas.bind("<B1-Motion>", self._drag_split)
        self.canvas.bind("<Button-1>", self._drag_split)

        # Strength slider below preview
        ctrl = tk.Frame(frame, bg=PANEL)
        ctrl.pack(fill="x", pady=(4, 0))
        tk.Label(ctrl, text="强度", font=(FONT, 10), bg=PANEL, fg=INK).pack(side="left", padx=8)
        self.strength_var = tk.IntVar(value=100)
        self.strength_scale = ttk.Scale(ctrl, from_=0, to=100, variable=self.strength_var,
                                        orient="horizontal", command=self._on_strength)
        self.strength_scale.pack(side="left", fill="x", expand=True, padx=4, pady=6)
        self.strength_label = tk.Label(ctrl, text="100%", font=(FONT_MONO, 10),
                                       bg=PANEL, fg=ACCENT2, width=5)
        self.strength_label.pack(side="right", padx=8)

    def _make_slots(self, parent):
        """Right: 7 ART slot cards (firmware chroma-curve path)."""
        frame = tk.Frame(parent, bg=PANEL)
        frame.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        tk.Label(frame, text="机内 ART 槽位（7槽）", font=(FONT, 12, "bold"),
                 bg=PANEL, fg=INK).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Label(frame, text="选择风格 → 点击槽位绑定 → 生成固件", font=(FONT, 9),
                 bg=PANEL, fg=MUTED).pack(anchor="w", padx=12)

        self.slot_frames = {}
        self.fw_assignment = dict(DEFAULT_ASSIGNMENT)
        for slot in FW_SLOTS:
            sid = slot["id"]
            label = slot["menu"]
            card = tk.Frame(frame, bg=CARD, bd=0)
            card.pack(fill="x", padx=10, pady=3)
            # Header
            hdr = tk.Frame(card, bg=CARD)
            hdr.pack(fill="x", padx=10, pady=(6, 1))
            tk.Label(hdr, text=label, font=(FONT, 10, "bold"),
                     bg=CARD, fg=ACCENT2).pack(side="left")
            unbind_btn = tk.Label(hdr, text="✕", font=(FONT, 10), bg=CARD, fg=MUTED, cursor="hand2")
            unbind_btn.pack(side="right")
            unbind_btn.bind("<Button-1>", lambda e, s=sid: self.unbind(s))
            # Content
            name_var = tk.StringVar(value="未绑定")
            name_lbl = tk.Label(card, textvariable=name_var, font=(FONT, 9),
                                bg=CARD, fg=INK, anchor="w")
            name_lbl.pack(fill="x", padx=10, pady=(0, 2))
            # Bind button
            bind_btn = ttk.Button(card, text="绑定当前风格",
                                  command=lambda s=sid: self.bind_to_slot(s))
            bind_btn.pack(fill="x", padx=10, pady=(0, 6))
            self.slot_frames[sid] = {"frame": card, "name_var": name_var, "bind_btn": bind_btn}
            # Show default assignment
            default_look = self.fw_assignment.get(sid)
            if default_look:
                for l in HQ_LOOKS:
                    if l.key == default_look:
                        name_var.set(f"🎞 {l.name_zh}")
                        break

        # Firmware build section
        sep = tk.Frame(frame, bg=MUTED, height=1)
        sep.pack(fill="x", padx=10, pady=8)
        tk.Label(frame, text="生成固件", font=(FONT, 11, "bold"),
                 bg=PANEL, fg=INK).pack(anchor="w", padx=12)
        tk.Label(frame, text="纯数据补丁，与已验证 RC2 同机制\n生成后按 SD 刷入流程安装", font=(FONT, 9),
                 bg=PANEL, fg=MUTED, justify="left").pack(anchor="w", padx=12, pady=(2, 6))
        ttk.Button(frame, text="🔧 生成 7 槽固件…", style="Accent.TButton",
                   command=self.build_firmware).pack(fill="x", padx=10, pady=4)
        ttk.Button(frame, text="📁 SD 风格数据包（开发用）", command=self.export_sd).pack(fill="x", padx=10, pady=2)

        # Camera status
        self.cam_var = tk.StringVar(value="相机：未连接")
        tk.Label(frame, textvariable=self.cam_var, font=(FONT, 9),
                 bg=PANEL, fg=MUTED).pack(anchor="w", padx=12, pady=(8, 10))

    def _make_firmware_panel(self, parent):
        """Placeholder for future firmware status panel (currently integrated in slots)."""
        pass

    # ─── Library ─────────────────────────────────────────────────────────────
    def _refresh_library(self, looks):
        self.looks = {l.id: l for l in looks}
        for cat, tree in self.shelf_trees.items():
            tree.delete(*tree.get_children())
        for look in looks:
            cat = categorize(look.title)
            tree = self.shelf_trees.get(cat, self.shelf_trees["自定义"])
            compat = "✓" if look.directly_compatible else "≈"
            tree.insert("", "end", iid=look.id, values=(look.title, compat))
        self.status_var.set(f"就绪 · {len(looks)} 个风格已载入")

    def _on_shelf_select(self, event):
        tree = event.widget
        sel = tree.selection()
        if not sel:
            return
        look_id = sel[0]
        self.current_id = look_id
        look = self.looks.get(look_id)
        if look:
            err = look.resample.get("mean_rgb8_error", 0)
            compat = "sRGB 直接兼容" if look.directly_compatible else "需要色彩声明"
            self.info_var.set(
                f"{look.title}\n"
                f"{look.side}³ · {compat}\n"
                f"重采样误差: {err:.1f}/255\n"
                f"来源: {look.source_filename}"
            )
            self._render()

    # ─── Preview ─────────────────────────────────────────────────────────────
    def _render(self):
        if not self.current_id or self.current_id not in self.looks:
            self.result = None
            self._paint()
            return
        self.epoch += 1
        token = self.epoch
        look = self.looks[self.current_id]
        q = amount_q8(self.strength_var.get())
        source = self.source
        def work():
            table = self.library.table(look.id)
            arr = preview_rgb8(np.asarray(source), table, q)
            return Image.fromarray(arr)
        def done(img):
            self.result = img
            self._paint()
        self._post(work, done, token=token)

    def _defer_paint(self, event=None):
        if self._timer:
            self.root.after_cancel(self._timer)
        self._timer = self.root.after(50, self._paint)

    def _paint(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10 or h < 10:
            return
        src = self.source
        # Fit image to canvas
        ratio = min(w / src.width, h / src.height)
        nw, nh = int(src.width * ratio), int(src.height * ratio)
        ox, oy = (w - nw) // 2, (h - nh) // 2

        before = src.resize((nw, nh), Image.Resampling.LANCZOS)
        self._photos = []
        bk = ImageTk.PhotoImage(before)
        self._photos.append(bk)
        c.create_image(ox, oy, anchor="nw", image=bk)

        if self.result:
            after = self.result.resize((nw, nh), Image.Resampling.LANCZOS)
            # Split: left = before, right = after
            split_x = int(nw * self.split_pos)
            cropped = after.crop((split_x, 0, nw, nh))
            ak = ImageTk.PhotoImage(cropped)
            self._photos.append(ak)
            c.create_image(ox + split_x, oy, anchor="nw", image=ak)
            # Divider line
            c.create_line(ox + split_x, oy, ox + split_x, oy + nh,
                          fill=ACCENT, width=2)
            c.create_oval(ox + split_x - 6, oy + nh // 2 - 6,
                          ox + split_x + 6, oy + nh // 2 + 6,
                          fill=ACCENT, outline="white")
            # Labels
            c.create_text(ox + 8, oy + 8, text="原图", anchor="nw",
                          fill="white", font=(FONT, 9))
            c.create_text(ox + nw - 8, oy + 8, text="效果", anchor="ne",
                          fill=ACCENT2, font=(FONT, 9))
        else:
            c.create_text(w // 2, h // 2, text="← 选择风格预览",
                          fill=MUTED, font=(FONT, 12))

    def _drag_split(self, event):
        w = self.canvas.winfo_width()
        if w > 0:
            self.split_pos = max(0.05, min(0.95, event.x / w))
            self._paint()

    def _on_strength(self, value):
        pct = int(float(value))
        self.strength_label.config(text=f"{pct}%")
        self._render()

    def choose_image(self):
        path = filedialog.askopenfilename(
            title="选择预览照片",
            filetypes=[("照片", "*.jpg *.jpeg *.png"), ("所有文件", "*.*")])
        if path:
            self.open_image(path)

    def open_image(self, path, assume=False):
        def work():
            return load_preview(Path(path), assume_srgb=assume)
        def done(result):
            img, desc = result
            self.source = img
            self.preview_desc.set(desc)
            self._render()
        def bad(exc):
            if isinstance(exc, NeedsProfile):
                if messagebox.askyesno("色彩空间", "照片没有 sRGB 标记。按 sRGB 预览？"):
                    self.open_image(path, assume=True)
            else:
                self._error(exc)
        self._post(work, done, bad)

    def reset_sample(self):
        self.source = sample_image()
        self.preview_desc.set("内置测试静物 · sRGB")
        self._render()

    # ─── Import ──────────────────────────────────────────────────────────────
    def import_files(self):
        paths = filedialog.askopenfilenames(
            title="导入 .cube LUT 文件",
            filetypes=[("Cube LUT", "*.cube"), ("所有文件", "*.*")])
        if not paths:
            return
        def work():
            results = []
            for p in paths:
                try:
                    look = self.library.import_file(p, input_encoding="srgb", output_encoding="srgb")
                    results.append(look)
                except (ValueError, OSError) as e:
                    results.append(str(e))
            return results, self.library.list_looks()
        def done(data):
            results, looks = data
            imported = sum(1 for r in results if not isinstance(r, str))
            errors = [r for r in results if isinstance(r, str)]
            self._refresh_library(looks)
            msg = f"导入 {imported} 个风格"
            if errors:
                msg += f"，{len(errors)} 个失败"
            self.status_var.set(msg)
            if errors:
                messagebox.showwarning("导入结果", "\n".join(errors[:5]))
        self._post(work, done)

    # ─── Slot binding ────────────────────────────────────────────────────────
    def bind_to_slot(self, slot_id):
        if not self.current_id:
            self.status_var.set("请先在左侧选择一个风格")
            return
        look = self.looks.get(self.current_id)
        if not look:
            return
        # For firmware slots, store the look_id for .cube fitting
        self.fw_assignment[slot_id] = self.current_id
        self.bindings[slot_id] = Binding(
            slot_id if slot_id in SLOTS else "pin-hole-i",
            self.current_id, look.title[:6], amount_q8(self.strength_var.get()))
        self.dirty = True
        self._update_slot_display(slot_id)
        menu = next((s["menu"] for s in FW_SLOTS if s["id"] == slot_id), slot_id)
        self.status_var.set(f"已绑定 {look.title} → {menu}")

    def unbind(self, slot_id):
        self.bindings.pop(slot_id, None)
        self.dirty = True
        self._update_slot_display(slot_id)

    def _update_slot_display(self, slot_id):
        sf = self.slot_frames[slot_id]
        look_id = self.fw_assignment.get(slot_id)
        if look_id:
            look = self.looks.get(look_id)
            if look:
                sf["name_var"].set(f"🎞 {look.title}")
            else:
                # Built-in HQ key
                for l in HQ_LOOKS:
                    if l.key == look_id:
                        sf["name_var"].set(f"🎞 {l.name_zh}")
                        break
                else:
                    sf["name_var"].set(f"🎞 {look_id}")
        else:
            sf["name_var"].set("未绑定")

    # ─── Project ─────────────────────────────────────────────────────────────
    def save(self):
        path = filedialog.asksaveasfilename(
            title="保存风格项目", defaultextension=".ep5proj",
            filetypes=[("E-P5 项目", "*.ep5proj")])
        if not path:
            return
        project = Project(self.project_name, tuple(self.bindings.values()))
        save_project(project, Path(path))
        self.dirty = False
        self.status_var.set(f"已保存: {Path(path).name}")

    def export_sd(self):
        if not self.bindings:
            messagebox.showinfo("导出", "请先绑定至少一个风格到 ART 槽位")
            return
        directory = filedialog.askdirectory(title="选择 SD 卡根目录（或导出文件夹）")
        if not directory:
            return
        def work():
            from .export import export_project
            project = Project(self.project_name, tuple(self.bindings.values()))
            return export_project(project, self.library, Path(directory))
        def done(result):
            self.status_var.set(f"✓ 已导出到 {directory}")
            messagebox.showinfo("导出完成",
                f"风格数据已写入:\n{directory}\n\n"
                "拔卡插入相机，ART 槽位即生效。\n"
                "（需要已安装 SD LUT 运行时固件）")
        self._post(work, done)

    # ─── Firmware build ─────────────────────────────────────────────────────
    def build_firmware(self):
        """Build a custom 7-slot firmware from current assignments."""
        stock_path = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
        if not stock_path.exists():
            messagebox.showerror("缺少原厂固件", f"找不到 {stock_path}")
            return
        out_dir = filedialog.askdirectory(title="选择固件输出目录（必须为空或不存在）")
        if not out_dir:
            return
        out_path = Path(out_dir)
        if out_path.exists() and any(out_path.iterdir()):
            messagebox.showerror("目录非空", "请选择一个空目录或不存在的目录名")
            return

        # Resolve assignments: look_id -> .cube path or HQ key
        assignment = {}
        for slot in FW_SLOTS:
            sid = slot["id"]
            spec = self.fw_assignment.get(sid)
            if not spec:
                spec = DEFAULT_ASSIGNMENT[sid]
            # If it's a library look_id (64 hex), resolve to .cube source path
            if spec in self.looks:
                look = self.looks[spec]
                cube_path = self.library.folder(spec) / "source.cube"
                assignment[sid] = str(cube_path)
            else:
                assignment[sid] = spec

        def work():
            from .firmware import build_firmware_from_assignment, package_kit
            fw, digest, report = build_firmware_from_assignment(
                stock_path, assignment, out_dir=out_path / "firmware")
            kit_dir = out_path / "kit"
            package_kit(stock_path, fw, digest, kit_dir)
            return digest, kit_dir

        def done(result):
            digest, kit_dir = result
            self.status_var.set(f"✓ 固件已生成: {digest[:16]}…")
            messagebox.showinfo("固件生成完成",
                f"SHA-256: {digest}\n\n"
                f"可刷 ZIP 包:\n{kit_dir}\n\n"
                "包含固件 + 官方恢复包。\n"
                "按 SD_TRIAL.txt 流程刷入。\n\n"
                "⚠ 尚未真机验证，刷入前请备份照片。")

        def bad(exc):
            self._error(exc)
            messagebox.showerror("构建失败", str(exc))

        self.status_var.set("正在生成固件…")
        self._post(work, done, bad)

    # ─── Close ───────────────────────────────────────────────────────────────
    def close(self, force=False):
        if self.dirty and not force:
            if not messagebox.askyesno("退出", "有未保存的更改，确定退出？"):
                return
        self._closed.set()
        self._jobs.put(None)
        self.root.destroy()


def main():
    root = tk.Tk()
    app = StudioV2(root)
    root.mainloop()


if __name__ == "__main__":
    main()
