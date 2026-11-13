import hashlib
import unittest

import numpy as np

from ep5studio.cube import Cube, compile_rgb17
from ep5studio.preview import preview_rgb8, resample_report


class StudioPreviewTests(unittest.TestCase):
    def test_firmware_c_golden_raster(self):
        # Hash obtained by running firmware/lut.c:ep5_lut_rgb8 on this exact
        # LUT/input with cc -std=c99 -O2 under WSL. All RGB bytes participate.
        i = np.arange(17**3*3,dtype=np.int64)
        table = ((i*1051 + 871*(i//17)**2 + 113*(i//289)) & 65535).astype("<u2").tobytes()
        i = np.arange(257*3,dtype=np.int64)
        img = ((i*53 + (i//3)*i*11) & 255).astype(np.uint8).reshape(1,257,3)
        result = preview_rgb8(img,table)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         "eb120f4b5e87d2560cb214bacbcd8494498f6c9abc25434b2bd218917d745296")

    def test_zero_half_and_full_strength_both_delta_signs(self):
        table = np.tile([65535,0,0],17**3).astype("<u2").tobytes()
        pix = np.array([[[0,255,128]]],dtype=np.uint8)
        np.testing.assert_array_equal(preview_rgb8(pix,table,128),[[[128,127,64]]])
        np.testing.assert_array_equal(preview_rgb8(pix,table),[[[255,0,0]]])
        bypass = preview_rgb8(pix,table,0)
        np.testing.assert_array_equal(bypass,pix)
        self.assertFalse(np.shares_memory(bypass,pix))
        np.testing.assert_array_equal(pix,[[[0,255,128]]])

    def test_original_grid_detail_invisible_to_runtime_is_reported(self):
        # Every even source knot is black, all odd R knots are red: decimation
        # onto 17^3 loses the entire pattern despite perfect agreement at vertices.
        data = np.zeros((33,33,33,3),np.float64)
        data[:,:,1::2,0] = 1.
        c = Cube("detail",33,data)
        result = resample_report(c,compile_rgb17(c))
        self.assertGreaterEqual(result["max_rgb8_error"],250)
        self.assertGreater(result["mean_rgb8_error"],30)
        self.assertEqual(result["sample_count"],33**3)
        self.assertFalse(result["camera_calibrated"])

    def test_identity_quality_and_non_contiguous_image(self):
        b,g,r = np.indices((2,2,2),dtype=float)
        c = Cube("identity",2,np.stack((r,g,b),axis=-1))
        table = compile_rgb17(c)
        src = np.arange(255,dtype=np.uint8).reshape(5,17,3)[:,::2,::-1]
        np.testing.assert_array_equal(preview_rgb8(src,table),src)
        self.assertEqual(resample_report(c,table)["max_rgb8_error"],0)

    def test_bypass_does_not_hide_bad_table_shape_or_amount(self):
        table = bytes(29478)
        img = np.zeros((1,1,3),np.uint8)
        for pixels,raw,amount in [(img,b"",0),(img,table,-1),(img,table,257),(img,table,True),
                                  (img.astype(float),table,0),(img[:,0],table,256),(img[:0],table,256)]:
            with self.assertRaises(ValueError):
                preview_rgb8(pixels,raw,amount)
