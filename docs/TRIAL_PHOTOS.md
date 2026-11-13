# 柔彩候选：检查机内直出的原始照片

**刷前就可以做第一步。** 找一处光线稳定的场景，放入灰卡和一两个鲜艳、没有过曝的色块。固定机位、构图、ISO、曝光和白平衡，选 ART → 针孔 I、4:3 最大尺寸、RAW+JPEG，按一次快门。把卡上的同编号 JPG 和 ORF 原样复制到电脑的 `sessions/before/`。刷后用相同设置和场景重新拍摄，复制到 `sessions/after/`。保留拍摄时的设置和菜单记录。若通过项目已有的 USB/Wi-Fi 工具采集，也可把下面的 JPG 路径换成采集目录中的实际路径。

在仓库根目录运行；Windows 可直接用 Python 3.11。下面的编号是示例，两个阶段的编号不必相同；每个阶段的 JPG 与 ORF 要在同一目录且同名。检查不需要连接相机，也不会修改照片。

```console
python -m pip install Pillow rawpy "simplejpeg>=1.9.0"
python tools/check_trial_photos.py --before sessions/before/P1010001.JPG
python tools/check_trial_photos.py --before sessions/before/P1010001.JPG --after sessions/after/P1010002.JPG --out sessions/pinhole-I.json
```

程序读取 JPG 和 ORF 各自的厂商、型号、原始拍摄时间；同组时间必须一致。它使用 [simplejpeg 的严格解码](https://github.com/jfolz/simplejpeg#decode_jpeg)读取主 JPEG 的全部 4608×3456 像素，拒绝可被普通解码器用灰色填补的意外截断，并用 [rawpy / LibRaw](https://letmaik.github.io/rawpy/api/rawpy.RawPy.html)解包可见传感器阵列。报告列出两份文件的 SHA-256、传感器尺寸及样本值范围。不同阶段误传同一份 JPG 或 ORF 将报错。本工具针对快门直出的 RAW+JPEG；机内重显影会另存不同编号，应作为另一项对照保存。

报告中的 `camera_settings` 另保留 Olympus MakerNote 的 PictureMode／ArtFilter 原始数值；按 [ExifTool 的 Olympus 标签定义](https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Olympus.pm)解释当前已知的 Natural、针孔 I／II／III。不支持或缺少标签会标明，不等同于“滤镜关闭”。ArtFilter 是实际滤镜标记：针孔 I 也可以同时记录基础 PictureMode 为 Natural，不能单看后者判断未开 ART。

2026-11-13 的[候选刷入前实测](mtp-art-baseline.json)已核对两张针孔 I 与两张 Natural，四组同号 ORF／全尺寸 JPEG 完整解码通过。构图有移动且使用自动白平衡，适合作为文件与模式基线，尚不能用来拟合精确颜色变换。

要检查颜色，请在**未自动旋转**的 JPG 中选定一块均匀颜色区域，记下左上角坐标和宽、高。将 `--region X Y 宽 高` 加到上面最后一条命令，可重复指定灰色和鲜艳色块；不指定时统计整幅图。报告的 `mean_rgb_spread_delta` 是每个区域内像素 RGB 最大通道减最小通道的平均值，取“刷后减刷前”。负数表示该区域的通道差缩小，不能直接解释为 ISP 的 LUT 数值。先对照报告中的曝光、焦距、白平衡模式和缺失项，再肉眼比较原图和灰阶。白平衡模式相同也不能证明色温和实际光照相同。构图错位、光线变化或重新压缩都可能改变结果。

`two_original_pairs_decoded` 只表示两组文件符合这些检查，照片可编辑的 EXIF 也不是来源认证。即使两个 JPEG 的像素有差异，报告仍保留 `firmware_installation: unverified`。请另外实测并记录[菜单显示、普通模式及针孔 II/III、重启和回刷](SOFT_CHROME.md)。如要保留多轮报告，需要为 `--out` 指定新的文件名。

开发者可运行 `python -m unittest discover -s tests -p test_check_trial_photos.py -v`。可选的真实 ORF 解码用例使用 [raw.pixls.us 公开的 CC0 E-P5 色卡样本](https://raw.pixls.us/getfile.php/1090/nice/Olympus%20-%20E-P5%20-%2016bit%20%284%3A3%29.ORF)；把环境变量 `EP5_CC0_ORF` 设为下载文件的本地路径再运行即可。其已知 SHA-256 以 `a1345ebe` 开头，完整可见阵列为 4640×3472。它用于验证解码流程，不是柔彩候选的样片。
