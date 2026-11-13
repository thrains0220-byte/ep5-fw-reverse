from pathlib import Path
import tempfile
import struct
import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageCms

from ep5studio.app import amount_q8, export_available, load_preview, NeedsProfile, sample_image
from ep5studio.project import Binding


class StudioAppTests(unittest.TestCase):
    def test_export_gates_empty_missing_and_incompatible_looks(self):
        b=Binding("pin-hole-i","a"*64,"测试",128)
        bindings={b.slot_id:b}
        self.assertFalse(export_available({},{}))
        self.assertFalse(export_available(bindings,{}))
        self.assertFalse(export_available(bindings,{b.look_id:SimpleNamespace(directly_compatible=False)}))
        self.assertTrue(export_available(bindings,{b.look_id:SimpleNamespace(directly_compatible=True)}))
        self.assertEqual([amount_q8(x) for x in (0,25,50,75,100)],[0,64,128,192,256])

    def test_display_copy_of_untagged_png_needs_explicit_assumption(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"原照片.png"
            im=Image.new("RGB",(1600,1000),(91,121,77))
            im.save(path)
            original=path.read_bytes()
            with self.assertRaises(NeedsProfile):load_preview(path)
            display,label=load_preview(path,True)
            self.assertLessEqual(display.width,1200)
            self.assertLessEqual(display.height,900)
            self.assertEqual(display.mode,"RGB")
            self.assertIn("sRGB",label)
            self.assertEqual(path.read_bytes(),original)

    def test_embedded_profile_converts_and_bad_icc_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"icc.png";im=Image.new("RGB",(12,8),(44,65,98))
            profile=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            im.save(path,icc_profile=profile)
            result,label=load_preview(path)
            self.assertIn("ICC",label)
            np.testing.assert_allclose(result.getpixel((0,0)),(44,65,98),atol=1)
            # Replace this synthetic test profile's three shared sRGB TRCs
            # with gamma=1.0. Linear RGB 0.5 becomes ~188 in display sRGB.
            linear=bytearray(profile)
            for j in range(struct.unpack_from(">I",linear,128)[0]):
                name,offset,size=struct.unpack_from(">4sII",linear,132+j*12)
                if name in (b"rTRC",b"gTRC",b"bTRC"):
                    linear[offset:offset+16]=b"para"+bytes(8)+b"\x00\x01\x00\x00"
            Image.new("RGB",(10,10),(128,128,128)).save(path,icc_profile=bytes(linear))
            converted,_=load_preview(path)
            np.testing.assert_allclose(converted.getpixel((0,0)),(188,188,188),atol=1)
            im.save(path,icc_profile=b"not-an-ICC-profile")
            with self.assertRaisesRegex(ValueError,"ICC"):load_preview(path,True)

    def test_initial_scene_has_visible_chroma_and_neutral_samples(self):
        rgb=np.asarray(sample_image(),dtype=np.int16)
        spread=rgb.max(axis=2)-rgb.min(axis=2)
        self.assertTrue((spread>90).any())
        self.assertTrue((spread<12).any())
