import itertools
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from tools.compare_capture_frame import compare_capture
from tools.render_sd_photo import frame_from_image


class CaptureFrameTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.frame = Path(temp.name) / "scene.yuv"
        self.jpeg = Path(temp.name) / "scene.jpg"
        self.w, self.h = 128, 96
        rng = np.random.default_rng(2044)
        patches = rng.integers(15, 241, (self.h//8, self.w//8, 3), dtype=np.uint8)
        self.scene = np.repeat(np.repeat(patches, 8, axis=0), 8, axis=1)

    def reference(self, scene):
        Image.fromarray(scene).save(self.jpeg, quality=98, subsampling=0)

    def test_all_sixteen_layouts_with_padded_rows(self):
        self.reference(self.scene)
        # Independent forward encoders. Full-range BT.601 uses the existing
        # renderer fixture; BT.709 comes from RGB-to-YCbCr coefficients.
        rgb = self.scene.astype(float) / 255
        for matrix, limits in itertools.product(("BT.601","BT.709"), ("full","limited")):
            if matrix == "BT.601":
                data = frame_from_image(Image.fromarray(self.scene))
                canon = np.frombuffer(data, np.uint8).reshape(self.h, self.w//2, 4).copy()
            else:
                y = np.dot(rgb, [0.2126,0.7152,0.0722])
                u = np.dot(rgb, [-0.114572,-0.385428,0.5]).reshape(self.h,-1,2).mean(axis=-1)
                v = np.dot(rgb, [0.5,-0.454153,-0.045847]).reshape(self.h,-1,2).mean(axis=-1)
                canon = np.rint(np.stack((255*y[:,::2],128+255*u,255*y[:,1::2],128+255*v),
                                         axis=-1)).clip(0,255).astype(np.uint8)
            if limits == "limited":
                canon[...,::2] = np.rint(canon[...,::2] * (219/255) + 16)
                canon[...,1::2] = np.rint((canon[...,1::2].astype(float)-128) * (224/255) + 128)
            for order, sequence in (("YUYV",[0,1,2,3]),("UYVY",[1,0,3,2]),
                                    ("YVYU",[0,3,2,1]),("VYUY",[3,0,1,2])):
                with self.subTest(order=order, matrix=matrix, limits=limits):
                    stride = self.w*2 + 12
                    rows = np.full((self.h,stride), 91, dtype=np.uint8)
                    rows[:,:self.w*2] = canon[...,sequence].reshape(self.h,-1)
                    self.frame.write_bytes(rows.tobytes()[:-12])
                    report = compare_capture(self.frame, self.jpeg, self.w, self.h, stride)
                    self.assertEqual(report["candidate"], dict(order=order,matrix=matrix,range=limits),
                                     report["reasons"])

    def test_gray_weak_colour_wrong_frame_and_local_mismatch(self):
        gray = np.repeat(self.scene[:,:,:1], 3, axis=2)
        weak = gray.copy()
        weak[:,:,0] = weak[:,:,0] + 2
        partial = self.scene.copy()
        partial[:self.h//2,:self.w//2] = 255 - partial[:self.h//2,:self.w//2]
        for frame, ref, reason in ((gray,gray,"insufficient_luma_or_colour_signal"),
                                   (weak,weak,"insufficient_luma_or_colour_signal"),
                                   (self.scene,np.roll(self.scene,16,axis=1),"poor_same_frame_fit"),
                                   (self.scene,partial,"poor_same_frame_fit")):
            with self.subTest(reason=reason):
                self.reference(ref)
                self.frame.write_bytes(frame_from_image(Image.fromarray(frame)))
                report = compare_capture(self.frame, self.jpeg, self.w, self.h)
                self.assertIsNone(report["candidate"])
                self.assertIn(reason, report["reasons"])

    def test_reject_unaligned_dimensions_and_truncated_file(self):
        self.reference(self.scene)
        data = frame_from_image(Image.fromarray(self.scene))
        for w,h,stride,buf in ((self.w+1,self.h,None,data),(self.w,self.h,self.w*2-1,data),
                               (self.w,self.h,None,data[:-1]),(self.w//2,self.h,None,data[:len(data)//2])):
            self.frame.write_bytes(buf)
            with self.assertRaises(ValueError):
                compare_capture(self.frame,self.jpeg,w,h,stride)
