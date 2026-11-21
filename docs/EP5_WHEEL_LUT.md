# E-P5 十二色区 LUT

工作色域采用归一化的 sRGB 显示 RGB。机内 UI 和电脑编译器共用的配方约定如下。

| JSON 字段 | 值 | 正方向 |
| --- | --- | --- |
| `sat` | 12 个整数，−5 至 +5 | 增加所选颜色的饱和度 |
| `hue` | 12 个整数，−15 至 +15 | 在 BT.601 的 Cb/Cr 平面中增大色相角，每档 5.5° |
| `light` | 12 个整数，−15 至 +15 | 提亮所选颜色，越接近无彩色影响越小 |

三个数组共用色区顺序，从索引 0 起依次是黄、橙、橙红、红、品红、紫、蓝、蓝青、青、绿青、绿、黄绿。数值 0 表示不做调整。表格采用上游饱和度标准范围和色相、明度扩展范围。色相角的定义为 `atan2(Cr−128, Cb−128)`。例如在红色区域增加色相角会偏向橙色。E‑P5 的拨轮手感和最终 JPEG 颜色仍待真机比对。

**制作风格。** 安装 Python 和 NumPy 后，把下面的内容保存为 `wheel.json`。这组示例只让红色略偏橙，并轻微提亮。省略一个轴时，其十二个滑块均为零。可选的 `wb_shift` 接受 `a_b` 和 `g_m` 两个整数，范围为 −7 至 +7。

```json
{
  "name": "Warm reds",
  "hue":   [0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0],
  "light": [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
}
```

```powershell
python tools/caduceus_to_ep5.py --wheel-json wheel.json --cube build/wheel-rgb17/WarmReds.cube
```

本机有 Caduceus 彩色配方的参考副本，也可以直接按名称导出。可用键包括 `lib2_gold`、`lib2_portra`、`lib2_velvia`。新检出的仓库如需使用这些名称，可将上游的 `sim/recipes/library_v2.json` 和 `library_v3.json` 放在 `build/research/caduceus-ep7-main/sim/recipes/`。自定义 JSON 无需这两个文件。

```powershell
python tools/caduceus_to_ep5.py --recipe lib2_gold --cube build/wheel-rgb17/Gold.cube
```

在 LUT Studio 中导入导出的 `.cube`，将输入、输出都声明为 sRGB。Studio 会保存红轴变化最快的 17³ RGB16LE 色表，每份 29,478 字节。2026-11-21 已逐一导入上述三个风格，并核对各自色表哈希。中性配方经过 Studio 后与标准恒等表逐字节一致。单独编辑红色的测试覆盖增饱和、偏橙、提亮和压暗，并检查绿色和灰阶。

该导出包含十二色区和白平衡的色度变化。上游配方中的基础色调曲线、胶片颗粒和光晕需要在其他处理阶段实现。样例模拟显示 RGB，应用到相机前仍须确定取样缓冲的颜色编码，再用同一份 ORF 验证 JPEG。样表、Studio 编译和传感器/ISP 的实际精度分别验证。

数字参考来自 [Caduceus 的色轮与明度曲线](https://github.com/cakelesscoder/caduceus-ep7/blob/78dbbc433ba0d04f1c31376937a98abede881526/sim/pipeline.py) 和 [PEN‑F 饱和度预测](https://github.com/fishcu/oly_fw_analysis/blob/a61498eecba1125010956864acbefaa1e4ff5f9e/tests/fixtures/color-builder-reference.json)。两个项目均使用 Apache-2.0 许可。本地 v2 配方 JSON 的 SHA-256 为 `ecad3ffb50fc34e3ee65e079262e0b6f6e8a90fd0c27ae442a05818b385a6d4c`，参考饱和度 JSON 为 `1050ea29c787372ac5bf213810c59f245854a2bf1a4bcbd78684e0bfedbf61e8`。

## 三款风格的 SD 数据包

`build/wheel-rgb17/EP5-Wheel-Trio.zip` 包含三个风格原件、索引、带校验的色表和来源清单。同目录的 `card-root/EP5LUT/` 是本地模拟的卡目录，其中只有索引和三张色表。协议要求机内加载器支持 `EP5IDX02`。当前原厂固件和固定 ART 风格固件尚无读取此包的实机记录。

| 索引短名 | 预设分配 | 槽位编号／变体 | 强度 |
| --- | --- | --- | --- |
| Gold | 柔光 I | 103 / 1 | 256 / 256 |
| Portra | 淡化增亮 I | 102 / 1 | 256 / 256 |
| Velvia | 浓郁色调 I | 100 / 1 | 256 / 256 |

这些分配用于分别选取三个风格。能否绕开对应 ART 原有的处理，需要以接入后同一 ORF 的成片为准。`Neutral.cube` 是包之外的恒等色表，可用作第四个对照。

两次独立导出的 ZIP 逐字节相同，SHA-256 为 `8fbfd70fa690a6b95643c134445061e06ec59f6833eccdf3799623c84ebd4b3d`。每个风格的表哈希及索引回读记录位于同目录的 `wheel-trio-readback.json`。

同目录的 `Wheel-Trio-Natural-preview.jpg` 展示了本机留存的 E‑P5 原厂 `PB130083.JPG` 和三个风格的桌面对比。原片为 4608×3456、Exif sRGB、Natural、ART 关闭。将同一张原图缩至 660×495 后，分别应用 ZIP 读回的色表，强度 100%。照片中央的灰键帽和右上方的红色桌垫便于对比。Gold 和 Portra 的变化较小，Velvia 在红、蓝两色上更明显。后续评估肤色和日光下的颜色仍需要相应样张。

从仓库根目录运行以下命令。需要 Python 3.10 或以上版本和 NumPy。工具会下载锁定提交的配方 JSON，核对其 SHA-256，再在 `build/wheel-rgb17/` 生成数据包、三个风格原件、中性对照、项目和回读报告。个人照片留存在本机预览目录，构建输入仅需配方和仓库源码。

```powershell
python tools/build_wheel_trio.py
```

离线重建可使用 `python tools/build_wheel_trio.py --recipes 路径/library_v2.json`，同样核对固定的配方哈希。`--out 目录` 可指定空输出目录。重复运行会读回并比对已有文件；若内容不同，会报出文件路径并保留现有文件。若 ZIP 哈希与上文不同，程序会报告实际哈希并停止发布输出。本次复现使用 Python 3.11.9、NumPy 2.4.6 和 zlib 1.3.1。
