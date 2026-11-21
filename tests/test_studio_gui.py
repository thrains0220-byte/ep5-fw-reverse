"""Integration tests of our own Tk widgets and callbacks (no OS/UI automation)."""
import gc
import sys
import tempfile
import time
from pathlib import Path
import unittest
from unittest.mock import patch
from tkinter import TclError, Tk, ttk
from zipfile import ZipFile

from ep5studio.app import Studio
from ep5studio.app_v2 import BUNDLED_CARD, CardPackageEditor, StudioV2
from ep5studio.card_zip import verify_card
from ep5studio.export import validate_style_archive
from ep5studio.library import Library
from ep5studio.project import SLOTS, load_project
from ep5studio.wire import unpack_index


def descendants(parent):
    for widget in parent.winfo_children():
        yield widget
        yield from descendants(widget)


class TkIntegrationTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = Tk()
        except TclError as exc:
            if sys.platform != "win32" and "display" in str(exc):
                self.skipTest("Tk display unavailable")
            raise
        # A withdrawn root remains 1x1 on some platforms. Map the test window
        # fully transparent so Tk actually negotiates all child rectangles.
        self.root.withdraw()
        self.root.attributes("-alpha", 0.0)
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.folder.cleanup)
        self.folderpath = Path(self.folder.name)
        self.studio = Studio(self.root, Library(self.folderpath/"library"))
        self.addCleanup(self.close_studio)
        self.root.deiconify()
        self.pump(lambda: self.studio.start_ready and self.studio.result is not None)

    def close_studio(self):
        self.studio.close(force=True)
        self.studio._worker.join(timeout=3)

    def pump(self, done, timeout=12):
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            self.root.update()
            if self.studio._errors:
                self.fail("Unexpected app error: " + "; ".join(self.studio._errors))
            if done():return
            time.sleep(.015)
        self.fail(f"Timed out; status={self.studio.status.get()!r}")

    def test_action_geometry_default_and_minimum_window(self):
        default_size = self.root.winfo_width(), self.root.winfo_height()
        sizes = {default_size, tuple(self.root.minsize())}
        for width,height in sorted(sizes,reverse=True):
            self.root.geometry(f"{width}x{height}")
            self.root.update_idletasks()
            self.root.update()
            seen=set()
            for w in descendants(self.root):
                if not isinstance(w,(ttk.Button,ttk.Entry,ttk.Combobox,ttk.Scale)): continue
                with self.subTest(size=(width,height),widget=str(w),text=w.cget("text") if isinstance(w,ttk.Button) else ""):
                    self.assertTrue(w.winfo_ismapped(), f"Unmapped at {width}x{height}: {w}")
                    if isinstance(w,ttk.Button):
                        seen.add(w.cget("text"))
                        self.assertGreaterEqual(w.winfo_height(),w.winfo_reqheight()-1)
                        self.assertGreaterEqual(w.winfo_width(),w.winfo_reqwidth()-1)
                    x,y=w.winfo_rootx(),w.winfo_rooty()
                    r,b=x+w.winfo_width(),y+w.winfo_height()
                    parent=w.master
                    while parent is not None:
                        px,py=parent.winfo_rootx(),parent.winfo_rooty()
                        self.assertGreaterEqual(x,px);self.assertGreaterEqual(y,py)
                        self.assertLessEqual(r,px+parent.winfo_width())
                        self.assertLessEqual(b,py+parent.winfo_height())
                        parent=parent.master
            self.assertTrue({"保存项目","打开项目","生成刷机固件 · 尚不可用","导出开发用风格包…"} <= seen)
            self.assertTrue(all(min(c.winfo_width(),c.winfo_height())>64 for c in self.studio.canvases))

    def test_bind_save_reopen_and_export_real_callbacks(self):
        studio=self.studio
        warm=next(k for k,v in studio.looks.items() if "WarmNegative" in v.source_filename)
        identity=next(k for k,v in studio.looks.items() if "Identity" in v.source_filename)
        self.assertTrue(studio.export_btn.instate(["disabled"]))
        for slot,key,name,percent in [("pin-hole-i",warm,"柔光",50),("pin-hole-ii",identity,"中性",75)]:
            studio.tree.selection_set(key)
            self.pump(lambda: studio.current_id==key)
            studio.slot.set(SLOTS[slot]["label"])
            studio.short.set(name)
            studio.slider.set(percent)
            studio.bind_btn.invoke()
        self.assertEqual([x.amount_q8 for x in studio.project().bindings],[128,192])
        self.assertFalse(studio.export_btn.instate(["disabled"]))
        saved=self.folderpath/"双风格项目.json"
        with patch("ep5studio.app.filedialog.asksaveasfilename",return_value=str(saved)):
            studio.save()
        self.assertEqual(studio.project(),load_project(saved))
        studio.binding_tree.selection_set("pin-hole-i")
        studio.unbind();self.assertNotIn("pin-hole-i",studio.bindings)
        with patch("ep5studio.app.filedialog.askopenfilename",return_value=str(saved)), \
             patch("ep5studio.app.messagebox.askyesno",return_value=True):
            studio.open_project()
        self.assertFalse(studio.dirty)
        self.assertEqual(studio.project(),load_project(saved))
        output=self.folderpath/"双风格开发包.zip"
        with patch("ep5studio.app.filedialog.asksaveasfilename",return_value=str(output)):
            studio.export_btn.invoke()
            self.pump(lambda: not studio._busy and output.is_file())
        report=validate_style_archive(output)
        self.assertEqual(report["bindings"],2)
        self.assertEqual(report["looks"],2)
        self.assertFalse(report["camera_ready"])
        self.assertFalse(report["firmware_file_created"])


class StudioV2ExportTests(unittest.TestCase):
    def test_export_button_writes_distinct_bindings_and_reports_existing_file(self):
        try:
            root = Tk()
        except TclError as exc:
            if sys.platform != "win32" and "display" in str(exc):
                self.skipTest("Tk display unavailable")
            raise
        root.withdraw()
        self.addCleanup(gc.collect)  # Release Tk cycles before another worker starts.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            studio = StudioV2(root, Library(path / "library"))

            def pump(done):
                limit = time.monotonic() + 12
                while time.monotonic() < limit:
                    root.update()
                    if done():
                        return
                    time.sleep(.015)
                self.fail(studio.status_var.get())

            try:
                pump(lambda: len(studio.looks) >= 2)
                chosen = iter(studio.looks)
                for slot, strength in (("pinhole-i", 50), ("pinhole-ii", 75)):
                    studio.current_id = next(chosen)
                    studio.strength_var.set(strength)
                    studio.slot_frames[slot]["bind_btn"].invoke()
                button = next(w for w in descendants(root) if isinstance(w, ttk.Button) and
                              w.cget("text") == "导出 SD 风格包")
                destination = path / "胶片风格.zip"
                with patch("ep5studio.app_v2.filedialog.asksaveasfilename", return_value=""), \
                     patch("ep5studio.app_v2.messagebox.showinfo") as success:
                    button.invoke()
                    success.assert_not_called()
                with patch("ep5studio.app_v2.filedialog.asksaveasfilename",
                           return_value=str(destination)) as dialog, \
                     patch("ep5studio.app_v2.messagebox.showinfo") as success, \
                     patch("ep5studio.app_v2.messagebox.showerror") as error:
                    button.invoke()
                    pump(lambda: success.called or error.called)
                    error.assert_not_called()
                    self.assertEqual(dialog.call_args.kwargs["defaultextension"], ".zip")
                    self.assertIn("开发验证", success.call_args.args[1])
                    report = validate_style_archive(destination)
                    self.assertEqual(report["bindings"], 2)
                    self.assertFalse(report["camera_ready"])
                    with ZipFile(destination) as archive:
                        rows = unpack_index(archive.read("EP5LUT/INDEX.EP5"))
                    self.assertEqual([(r["picture_mode"], r["variant"], r["amount_q8"]) for r in rows],
                                     [(105, 1, 128), (105, 2, 192)])
                    original = destination.read_bytes()
                    success.reset_mock()
                    button.invoke()
                    pump(lambda: error.called)
                    success.assert_not_called()
                    self.assertIn("已存在", error.call_args.args[1])
                    self.assertEqual(destination.read_bytes(), original)
            finally:
                studio.close(force=True)
                studio._worker.join(timeout=3)

    def test_card_editor_adds_and_replaces_using_gui_controls(self):
        try:
            root = Tk()
        except TclError as exc:
            if sys.platform != "win32" and "display" in str(exc):
                self.skipTest("Tk display unavailable")
            raise
        root.withdraw()
        root.attributes("-alpha", 0.0)
        self.addCleanup(gc.collect)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            studio = StudioV2(root, Library(path / "library"))
            root.deiconify()
            root.update()

            def pump(done):
                limit = time.monotonic() + 12
                while time.monotonic() < limit:
                    root.update()
                    if done():
                        return
                    time.sleep(.015)
                self.fail("Studio v2 card editor timed out")

            def button(parent, name):
                return next(w for w in descendants(parent) if isinstance(w, ttk.Button) and w.cget("text") == name)

            _, original = verify_card(BUNDLED_CARD.read_bytes())
            source_counts = [len(b["looks"]) for b in original["banks"]]
            cube = path / "原创暖色.cube"
            cube.write_text("LUT_3D_SIZE 2\n0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n")
            editors = []
            try:
                with patch("ep5studio.app_v2.CardPackageEditor",
                           side_effect=lambda s: editors.append(CardPackageEditor(s))):
                    button(root, "编辑 SD 卡包…").invoke()
                editor, = editors
                pump(lambda: editor.source == BUNDLED_CARD)
                self.assertEqual(sum(source_counts), 32)
                self.assertLess(source_counts[editor.bank.current()], 14)
                self.assertIsNone(editor.slot_ids[editor.slot.current()])
                with patch("ep5studio.app_v2.filedialog.askopenfilename", return_value=str(cube)):
                    button(editor.window, "选择 .cube…").invoke()
                editor.save_button.invoke()
                self.assertIn("色域", editor.status.get())
                editor.srgb.set(True)
                bank = editor.bank.current()
                first_zip = path / "个人增补.zip"
                second_zip = path / "个人替换.zip"
                with patch("ep5studio.app_v2.filedialog.asksaveasfilename",
                           side_effect=[str(first_zip), str(second_zip)]), \
                     patch("ep5studio.app_v2.messagebox.showinfo") as success, \
                     patch("ep5studio.app_v2.messagebox.showerror") as error:
                    editor.save_button.invoke()
                    pump(lambda: error.called or editor.source == first_zip)
                    error.assert_not_called()
                    _, added = verify_card(first_zip.read_bytes())
                    self.assertEqual(len(added["banks"][bank]["looks"]), source_counts[bank] + 1)
                    self.assertEqual(added["banks"][bank]["looks"][-1]["label"], "原创暖色")
                    with patch("ep5studio.app_v2.filedialog.askopenfilename", return_value=str(first_zip)):
                        button(editor.window, "打开卡包…").invoke()
                    pump(lambda: error.called or editor.source == first_zip)
                    error.assert_not_called()
                    editor.bank.current(0)
                    editor.bank.event_generate("<<ComboboxSelected>>")
                    root.update()
                    target_index = next(i for i, key in enumerate(editor.slot_ids) if key is not None)
                    replaced_slot = editor.slot_ids[target_index]
                    editor.slot.current(target_index)
                    editor.label.set("替换新色")
                    editor.save_button.invoke()
                    pump(lambda: error.called or editor.source == second_zip)
                    error.assert_not_called()
                    self.assertEqual(success.call_count, 2)
                    _, result = verify_card(second_zip.read_bytes())
                    replacement = next(row for row in result["banks"][0]["looks"] if row["slot"] == replaced_slot)
                    self.assertEqual(replacement["label"], "替换新色")
                    self.assertEqual(sum(len(b["looks"]) for b in result["banks"]), 33)
                    self.assertFalse(result["camera_verified"])
            finally:
                studio.close(force=True)
                studio._worker.join(timeout=3)
