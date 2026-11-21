# Gold、Portra 与 Velvia 的参考色调

`build/recipe-color/EP5-Reference-Tone-Trio.zip` 是按 Caduceus 的显示 sRGB 预览生成的 Studio 数据包。它保留了三份参考配方对白平衡、对比度、高光、阴影、中间调和十二色区的设置。E-P5 的实际 JPEG 仍须使用同一份 ORF，通过机内重显影对照。此前的纯色轮样表适合检查单独调色，这一套能一起检查阴影和反差。

| 风格 | 高光 / 阴影 / 中间调 | 对比度 | 输入灰色 `(64,64,64)` 的参考预览 RGB8 | 未纳入色表的配方项 |
|---|---|---|---|---|
| Gold 200 | −1 / 0 / +1 | 0 | 72, 71, 70 | 低颗粒 |
| Portra 400 | −2 / +2 / +1 | −1 | 85, 84, 84 | 低颗粒，一级柔光 |
| Velvia | +1 / −4 / 0 | +2 | 40, 40, 40 | 无空间效果 |

这些配方属于 Caduceus `library_v2` 的彩色样式。三份数据都没有独立的 `mix` 或 `film_curve` 字段。相机的基础显影和胶片的逐色调节需要分别处理。输入已经经过显影并且使用显示 sRGB 时，使用上游网页的逐像素处理就能保留相对色调。实际取样点若提供线性 RGB 或其他编码，需要先匹配输入。相机的传感器、白平衡策略和 ISP 也会影响用同一张 LUT 得到的成片。

**重做数据包。** 准备 Python、NumPy 和 Node.js 24。在项目根目录运行以下命令。首次下载的六份上游文件固定在同一提交，读取前逐一校验 SHA-256，后续离线运行可省略 `--fetch-reference`。仅当需要一个样式时，加 `--look Gold`、`--look Portra400` 或 `--look Velvia`，并为该 ZIP 提供另一个文件名。

```powershell
python tools/export_recipe_color.py --fetch-reference --archive build/recipe-color/EP5-Reference-Tone-Trio.zip
python -m unittest discover -s tests -p test_recipe_color.py -v
```

**颜色验证。** 处理顺序直接采用作者的网页渲染代码。程序仅调整模块导入路径以便 Node 运行，再于最终显示量化前读取 RGB 浮点数。上游入口接收 8 位 sRGB，每个精确的 17³ 网格节点由相邻输入色码插值得出，避免将节点提前取整。Studio 导入后每张 RGB16LE 表为 29,478 字节。16 位表示表内的输出精度，输入参照和最终机内 JPEG 有各自的精度。

2026-11-21 已逐项对照上游原始 8 位显示输出，选用了灰阶、肤色方向、蓝、绿、暖黄共八个色块。另在种子 `21745` 的 8,192 个 RGB8 随机色块上，对比 17³ 插值与相同输入直接执行的参考渲染。误差单位为每通道的 8 位色码。

| 风格 | 平均绝对误差 | 第 95 百分位 | 最大绝对误差 |
|---|---:|---:|---:|
| Gold | 0.19 | 0.57 | 4.92 |
| Portra | 0.14 | 0.39 | 3.25 |
| Velvia | 0.33 | 1.85 | 6.26 |

这组数字衡量将参考颜色压成 17³ LUT 的误差。三款对应胶片实物的色差、E-P5 成片、颗粒和柔光的视觉效果需要分别验收。整个归档的 SHA-256 为 `909d5831f520140cfd4f435bb70a695e6aebbd2fe2e8cae257ceff5bc2c81cc3`，已通过 Studio 的结构和表校验。归档仅含风格数据。

本地对照图 `build/recipe-color/Tone-Trio-Natural-preview.jpg` 使用机主同一张原厂 Natural JPEG `PB130083.JPG`。将照片缩至 640×480 后，用从该 ZIP 读回的三张表分别以 100% 强度处理，机位、曝光和白平衡均相同。看黑色键盘的阴影最容易分辨 Portra 和 Velvia。原片与该对照图只保存在本地。

参考代码及配方取自 Caduceus 提交 `78dbbc433ba0d04f1c31376937a98abede881526`。来源可核对[三款 v2 配方](https://github.com/cakelesscoder/caduceus-ep7/blob/78dbbc433ba0d04f1c31376937a98abede881526/sim/recipes/library_v2.json)、[显示 sRGB 预览](https://github.com/cakelesscoder/caduceus-ep7/blob/78dbbc433ba0d04f1c31376937a98abede881526/webapp/src/preview.ts)和[显示亮度模型](https://github.com/cakelesscoder/caduceus-ep7/blob/78dbbc433ba0d04f1c31376937a98abede881526/webapp/src/tone.ts)。
