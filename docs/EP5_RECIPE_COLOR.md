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

## 发布版的 29 款彩色风格

首次运行以下命令，从发布清单 `bundles/library_v3.json` 读取 29 条彩色记录，按每条记录的配方编号读取 v2 或 v3 色彩参数，再应用发布清单指定的黑位、白位等调整。另有三条单色记录，保留在上游的单色库。数据包按当前索引可分配的 14 个位置分组。运行时只有本组所分配的位置可以选，每张 LUT 的预设强度都是 100%。

```powershell
python tools/export_recipe_color.py --release-library --fetch-reference --out build/caduceus29
```

| 文件 | 内含风格，上游排列顺序 |
| --- | --- |
| `EP5-Caduceus29-Bank01.zip` | Velvia、Astia、Classic Chrome、Classic Neg、Provia 400、Reala Ace、Eterna、Bleach Bypass、Kodachrome 64、Portra 400、Ektar 100、Gold 200、Ektachrome、CineStill 800T |
| `EP5-Caduceus29-Bank02.zip` | Pro 400H、Faux IR、Kodachrome 25、Portra 160、Fujicolor 200、Cuban Neg、Cibachrome、UltraMax 400、Agfa Vista、CineStill 50D、Vision3 250D、Vision3 500T、Polaroid、Cross Process |
| `EP5-Caduceus29-Bank03.zip` | Atrophy |

同目录 `catalog.json` 给出全名与机内短名、分组、每项分配的位置、色表哈希、上游作者标明的配方来源、需要单独实现的效果，以及逐色块的结果。`Caduceus-LICENSE.txt` 与 `Caduceus-NOTICE.txt` 随库保留。三包各使用相同的目录名和文件编号，两个包的 `EP5LUT` 目录不能直接合并。现阶段可用 Studio 查看各包中的 `.cube`，E-P5 从卡读取和实际 JPEG 仍须机内验收。

2026-11-21 实际导出 29 张不同的 RGB16LE 表，通过三个 ZIP 的索引与内容校验。从封装后的每张表生成灰阶和肤色等 9 个色块，加上 8,192 个随机 RGB8，再与上游相同输入的浮点预览比较。每款的平均单通道绝对误差落在 0.287 至 0.626 个 8 位色阶之间。误差最大的是 Faux IR，单通道最高 10，95 分位为 2.361。这个数值包括 17³ 采样及桌面参考中整型输出的量化，并不衡量 E-P5 胶片观感。19 款列有颗粒，8 款列有柔光，Atrophy 列有局部清晰度。此处记录这些配方意图，空间和纹理效果需要机内独立处理。

v3 发布清单和原三款取自同一提交，但样式设置可以不同。以输入 `(64,64,64)` 为例，读回 v3 表经 Studio 输出 Gold `(71,70,69)`、Portra `(83,82,82)`、Velvia `(36,36,36)`。原三款的命令继续产生原版 v2 ZIP，便于同源对照。[上游发布清单](https://github.com/cakelesscoder/caduceus-ep7/blob/78dbbc433ba0d04f1c31376937a98abede881526/bundles/library_v3.json)

## 一张卡保存全部 29 款

`build/caduceus29/EP5-Caduceus29-OneCard.zip` 包含三组可共存的卡上目录。第一组沿用 `EP5LUT/`，另两组分别放在 `EP5LUT/B02/` 和 `EP5LUT/B03/`。每个目录包含一份 `INDEX.EP5` 以及本组的编号色表，卡根的 `CATALOG.JSON` 保存全名和检查结果。带预设效果的 `EP5-Caduceus29-OneCard-FX.zip` 在每组目录内增加 `FX.EP5`。生成命令如下。

```powershell
python tools/export_recipe_color.py --combine-banks --out build/caduceus29
python tools/export_recipe_color.py --combine-banks --out build/caduceus29 --with-fx
```

2026-11-21 的普通单卡包 SHA-256 为 `5b4e0ed85e8a85dcd8c914fa769bb817e0c6a0dc4f9102ba78c363315870f92b`，带 FX 预设的包为 `b466f307d376496436640e06971cfb343c57f5ac58ace631cdb195af478fc5ae`。

`firmware/lut_bank.h` 定义分组选择器。文件任务先用 `ep5_lut_bank_browser_init` 建立三份固定目录视图。由 `ep5_lut_bank_next` 确定前一组或后一组，`ep5_lut_bank_select` 请求切组，`ep5_lut_bank_step` 推进后台读卡。读取完成后，原有菜单行和拍摄选择器使用本组名单。新组需要重新确认风格。切组过程中若有旧读卡尚未完成，新请求会返回零，调用方可以在结束或取消旧任务后重试。

WSL 上的两项 C 集成测试均通过。测试从实际单卡 ZIP 读取 29 张表，逐一比较 SHA-256，又用同一个菜单按 `1 → 2 → 3 → 1` 的顺序刷新名称和数量，覆盖读取中尝试切组、读到一半退出、缺少第二组索引时清空拍摄选择。第一组的旧目录名仍可按原方式读取。

2026-11-21 已修正 `ep5_art_entry.c` 中 `look_open` 的路径缓冲，并让分组和本机打开函数共用同一套文件名检查。三组共 54 个合法路径都按 `rb` 模式打开。第三组的 `C:\EP5LUT\B03\L0000016.LUT` 可完整送至文件后端。越界编号、未定义的组、穿越目录和过长名称均在打开前拒绝。`test_lut_bank` 的三项测试通过，其中实际 ZIP 的 29 张表经同一个 `look_open` 进入模拟文件后端并核对 SHA-256。原有 MN103 同步读取和预载拍摄两项回归通过。真实 ART 切组事件、原厂文件服务调度、换卡和退出仍待机内接入，直出需用同一 ORF 的全尺寸 JPEG 验收。
