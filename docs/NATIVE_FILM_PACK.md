# E-P5 1.8 原生胶片风格包（针孔 I 色度曲线）

本页记录一组**可直接刷入**的胶片色彩固件。它们复用已在一台 Olympus PEN E-P5 上验证过启动、全尺寸 RAW+JPEG 成片和官方恢复的 **RC2 色度曲线机制**，只把针孔 I 的两条原生色度曲线换成不同胶片取向，录像与其他模式保持原厂。**没有新增可执行代码、没有额外任务、不改亮度。**

相机当前保持官方 1.8。本包是 `hardware-functional-candidate`：机制已真机验证，但**这些新曲线尚未在相机实拍**。刷入前请阅读 [SD_TRIAL.txt](SD_TRIAL.txt) 与 [SOFT_CHROME.md](SOFT_CHROME.md) 的安装、灯态与恢复说明，并先备份照片、拍原厂对照。

## 能力边界（先读这条）

E-P5 针孔槽的原生处理是**两条一维色度曲线**（Cb 轴、Cr 轴各一条），作用于 YCbCr 的色度，**不改变亮度 Y**。它能表达：

- **饱和度缩放**（浓艳 / 低饱和 / 漂白）——核心手段，表达良好；
- **轻微暖/冷色度偏移**——会略微染灰阶，故偏移量保持很小；
- **完全去色黑白**（Cb/Cr→128）——表达精确。

它**不能**表达：亮度 S 曲线（高反差）、色相旋转（红→橙）、按亮度分离调色、颗粒、暗角。因此：

- **森山 / Tri-X 黑白**此版为**纯去色黑白**，标志性的高反差与颗粒不在色度曲线范围；反差请用机身对比度设置补足。
- 彩色风格是**取向近似**，不是胶片的逐像素复刻。下表给出量化误差。

任意 3D `.cube` 直出仍走 [SD LUT 运行时主线](../plans/EP5_LUT_DELIVERY_PLAN.md)，与本包是两条路；本包不读取 SD 上的 LUT。

## 风格与误差

误差在 17³ sRGB 网格上测量。「色度最大误差」是拟合曲线相对理想逐轴变换的最大偏差（0–255）；「RGB 平均误差」是硬件色度曲线结果相对完整 RGB 胶片目标（`ep5studio/filmlooks.py`）的平均差，含不可表达的亮度/色相/分离调色部分。

| 风格 key | 名称 | 饱和倍率 | Cb/Cr 偏移 | 色度最大误差 | RGB 平均误差 |
| --- | --- | --- | --- | --- | --- |
| gold200 | 柯达金200·暖负片 | 1.16 | -3/+5 | 12.4 | 10.1 |
| portra160 | 人像160·柔负片 | 0.90 | -1/+2 | 0.4 | 3.2 |
| velvia50 | 反转50·浓艳 | 1.42 | +0/+1 | 14.1 | 14.9 |
| classicchrome | 经典铬·纪实 | 0.82 | +1/-1 | 0.5 | 17.7 |
| ektar100 | 风景100·鲜艳 | 1.30 | +0/+0 | 14.0 | 8.4 |
| bleach | 银留·漂白 | 0.55 | +0/+0 | 0.4 | 33.0 |
| moriyama_bw | 森山·高反差黑白 | 0.00 | +0/+0 | 0.0 | 60.0 |
| trix_bw | Tri-X·报道黑白 | 0.00 | +0/+0 | 0.0 | 49.5 |

黑白与漂白的高 RGB 误差来自完整目标里的亮度 S 曲线/去色后反差，色度本身（去色/低饱和）是精确的。

## 色彩校准来源

取向参数参考公开胶片特征描述，非商业 LUT 复刻：

- **Kodak Gold 200**：暖金黄高光、桃色肤色、饱和偏高、灰阶近中性、最深阴影微冷。[Clack Gold 200 分析](https://clackcam.com/films/gold-200/) · [The Grain Archive darktable 风格测量](https://thegrainarchive.com/styles/kodak-gold-200/)（中调琥珀、高光暖、阴影微蓝、饱和+8%）· [analog.cafe 评测](https://www.analog.cafe/r/kodak-gold-film-review-chsw)。本包用饱和+16% 与极小暖偏移近似，灰阶保持近中性。
- **Portra 160**：柔和、低饱和、保护肤色暖调。
- **Velvia 50 / Ektar 100**：高饱和反转/风景负片。
- **Classic Chrome**：低饱和、硬调、微冷。
- **森山大道 / Tri-X 400**：高反差黑白取向（此版仅去色）。

这些是公开描述驱动的原创近似，未移入第三方商业风格文件或源码。

## 构建与校验

```bash
# 单个风格固件（新本地目录）
python tools/build_native_film_pack.py data/ep5-stock/OLY_E_108_1800_0000_0000.BIN \
  --look gold200 --label-zh 柯达金200 --label-zht 柯達金200 --out build/film-gold200

# 全部风格 + 官方恢复包，打成可刷 ZIP（逐包回读校验）
python tools/build_film_pack_kit.py data/ep5-stock/OLY_E_108_1800_0000_0000.BIN --out build/ep5-film-kit
```

每个固件构建时由 `film_update.build_update` 做容器往返校验（reconstruct + 重新解包 + 逐块比对）。原生写入器探针校验（WSL，需 cc）确认：

- 只有照片模式 73（针孔 I）的色度字变化；
- 录像模式 82 重指回原厂恒等表，录像保持原厂；
- 打包驱动字与生成曲线逐字节一致；
- 共享 CMIO 副本与 RC2 相同处理。

```bash
# WSL：逐风格写入器校验（需先用 build_probe 生成 build/chroma-dump/ep5-contract-probe）
bash tools/film_pack/verify_all.sh
# 回归
python -m unittest tests.test_native_film_pack tests.test_build_native_film tests.test_film_update
```

## 交付物

`build/ep5-film-kit/` 下 9 个 ZIP：8 个风格各一，加 `E-P5-1.8-STOCK-RECOVERY.zip`（官方 1.8，SHA-256 `cc59a4e1…b5cfd`）。每个 ZIP 含 `DCOLYMP/E1089999.BIN`（44,826,624 字节）、`SHA256SUMS`、`READ-ME.txt`。卡上路径与 RC2 相同，刷法见 SD_TRIAL.txt。

**一次只刷一个风格**（都占用针孔 I）。换风格即重刷对应包；回原厂用恢复包。三槽（针孔 I/II/III 各挂一个风格）需要 II/III 的隔离验证，尚未做，见 [ART_SLOT_AUDIT.md](ART_SLOT_AUDIT.md)。

## 三槽包（针孔 I/II/III 各一个风格）

`build/ep5-film-trio-kit/E-P5-1.8-Film-TRIO.zip` 把三个风格分别挂到针孔 I/II/III。E-P5 的 ART 菜单里**针孔相机只有一个条目**，I/II/III 是选中针孔后按**右方向键**切换的子变体，无法分别改名；READ-ME 里写明每个子变体对应哪个风格。

II/III 的色度表与共享选择器（107/109）相连，不能直接套用 I 的改法。三槽构建器按 I 的已验证结构对 II/III 做同样隔离：改照片模式 106/108 的曲线，把共享模式 107/109 重路由到原厂中性 case（模式 69），并重定向 CMIO 第二轴字面副本。**必须通过两项原生探针校验才可刷：**

```bash
# WSL：写入器校验——仅 73/106/108 变化，82/107/109 及其余模式保持原厂
PYTHONPATH=. python3 tools/film_pack/verify_trio.py
# WSL：完整拍摄路径校验——3 槽 × 录像状态 7/8/9，全幅分配/JPEG/转换器/驱动字
PYTHONPATH=. python3 tools/film_pack/verify_trio_route.py
```

当前三槽配置（已通过上述两项校验）：

| 子变体 | 风格 | 照片模式 | 共享模式（保持原厂） |
| --- | --- | --- | --- |
| 针孔 I | 柯达金200 | 73 | 82 |
| 针孔 II | 森山黑白 | 106 | 107 |
| 针孔 III | 浓艳反转50 | 108 | 109 |

```bash
# 重新构建三槽 kit（含官方恢复包）
python tools/build_film_trio_kit.py data/ep5-stock/OLY_E_108_1800_0000_0000.BIN \
  --i gold200 --ii moriyama_bw --iii velvia50 --out build/ep5-film-trio-kit
```

三槽包同样**未在相机实拍**；机制与隔离经探针证明，但具体色彩与取景一致性需上机对照。换其他风格组合时，重跑两项校验后再刷。

## 未验证 / 限制

- 这些曲线未在本台 E-P5 实拍；取景预览与最终 JPEG 是否一致需上机对照。
- 黑白的高反差、所有风格的颗粒/暗角/色相旋转不在色度曲线范围。
- 繁体菜单显示、针孔 II/III、长期稳定性未验证。
- 本包不读取 SD LUT；任意 `.cube` 直出是另一条主线。
