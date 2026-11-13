"""Integration tests of our own Tk widgets and callbacks (no OS/UI automation)."""
import sys
import tempfile
import time
from pathlib import Path
import unittest
from unittest.mock import patch
from tkinter import TclError, Tk, ttk

from ep5studio.app import Studio
from ep5studio.export import validate_style_archive
from ep5studio.library import Library
from ep5studio.project import SLOTS, load_project


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
