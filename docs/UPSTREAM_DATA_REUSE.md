# 两个上游项目的数据，哪些能直接拿来用

日期：2026-11-14
结论：**固件补丁的地址/代码不能照搬，但配方数据、色彩模型、表结构方法论可以直接参考。**
本文把「能用的数据」逐项列出，并给出映射到 E-P5 色度引擎的方法。

---

## 1. 能直接用的数据（已读到本机）

### A. Caduceus 胶片配方库（最有价值）
路径：`build/research/caduceus-ep7-main/sim/recipes/library_v2.json`、`library_v3.json`
每个 look 含：
- `sat[12]`、`hue[12]`、`light[12]`：12 扇区逐色饱和/色相/亮度，−7..7（实测调校）
- `tone {highlights, shadows, midtones, blacks, whites}`：tone 曲线
- `contrast`、`wb_shift {a_b, g_m}`、`grain`、`effect{bloom/halation/clarity}`

实例（已读出）：
| look | sat[12] | hue 特征 | wb_shift | tone |
|---|---|---|---|---|
| Velvia | 4,4,4,5,3,4,5,5,3,3,4,4 | 蓝+2 绿−2 | — | H+1 S−4 |
| Portra400 | −1,0,0,−1,−1,−2,−2,−2,−2,−3,−3,−2 | 肤暖 | a_b+1 | H−2 S+2 M+1 |
| Gold200 | 4,2,0,0,−1,−1,−2,−2,−3,−2,0,2 | 黄绿−2 | a_b+2 | H−1 M+1 |
| Cl.Chrome | −2,−1,−1,−1,−1,−3,−3,−3,−1,−3,−4,−4 | 青空 | — | S−3 |
| Ektar100 | 1,2,3,3,2,1,4,4,2,0,1,1 | 红蓝强 | — | S−1 |
| CineStill800 | −1,0,2,3,0,0,2,2,2,−1,−2,−2 | 冷调 | a_b−3 | H−1 S+2 |

**这些是它们用真机 JPEG 标定出来的胶片色彩，比我们自己设计曲线权威。**

### B. Caduceus 桌面色彩管线（转换模型）
路径：`sim/pipeline.py`、`sim/film.py`、`sim/effects.py`、`sim/base_curve.json`
- `base_curve.json`：从 12 张 E-P7 JPEG 拟合的相机基础 tone 曲线。
- `pipeline.py`：WB→bloom→halation→减色饱和→color_chrome→film_curve→tone→HSL→mono→vignette→grain 的完整顺序。
- `ep7_tone_model.py`：bit-exact 相机 H/S/M LUT 模型。
**用途**：我们写「配方→E-P5 表」转换器时，用它的色彩数学做参考实现。

### C. PEN-F HSL 表结构（最接近 E-P5 的参考）
路径：`build/research/oly_fw_analysis-main/docs/color/pen-f/HSL_TABLES.md`、`patches/hsl/pen-f/src/orf_metadata/cmio_tables.s`
- PEN-F COLOR 表：12 记录×28B + 4 LUT(96×u32) + 6 LUT(96×u16)。
- 12 扇区顺序、滑块→系数换算（H_native=−1000×H_slider，L 非线性表）。
- `cmio_capture_weights`：把 12 扇区 H/S/L 转成 CMIO P 系数的算法（mul/div 定点）。
**E-P5 用同族 CMIO 引擎**（本机 0x7e21c42c 代码、0x7e573000 数据块），所以这套换算方法论可借鉴。

### D. Caduceus look 文件格式 / SD 加载安全设计
路径：`docs/FILM_LIBRARY.md`、`docs/SD_BUNDLES_V3.md`、`patches/sd_bundles_v3/`
- LOOKS.BIN v2 格式（magic/CRC/逐字节范围校验）。
- sd_bundles_v3「不写 loaded image、malloc 池发布句柄、boot 不读卡」安全模式。
**用途**：阶段 C（SD 热换）直接借鉴格式与安全设计。

---

## 2. E-P5 色度引擎的真实结构（本机已核实）

ART 每个模式的 CMIO 块加载三类表（ dispatcher 0x7e21c000–0x7e221000 ）：
| 表族 | 地址 | 内容 | 我们已用 |
|---|---|---|---|
| 色度曲线 | 0x7e438xxx/0x7e439xxx | Cb/Cr 16 节点曲线（pair，49B×2） | ✅ safe-7 |
| **色度增益 ramp** | **0x7e453xxx** | 6×u16 饱和乘数（256=1.0×），多组逐色变体 | ❌ 没用 |
| **tone/gamma** | **0x7e4530c0 区 / 0x7e456xxx/0x7e457xxx** | 15,25,30…160,400,800 ramp + 0x3333 模式 | ❌ 没用 |

**关键：safe-7 只改了色度曲线，没改色度增益 ramp 和 tone。这就是色彩单薄的根因。**
E-P5 没有逐模式 3×3 RGB 矩阵（ART 路径），色彩丰富度靠「色度曲线 + 色度增益 ramp + tone」三层。

---

## 3. 数据映射方法（配方 → E-P5 表）

 Caduceus 的 12 扇区 sat/hue/light 不能原样塞进 E-P5（E-P5 没有 12 扇区 HSL 单元），
但可以**投影拟合**到 E-P5 的三层：

1. **sat[12] → 色度增益 ramp + 色度曲线**：
   12 扇区饱和按色相角投影到 Cb/Cr 两轴，拟合 16 节点曲线 + 6 级增益 ramp。
   （我们已有 `tools/cube_to_hq.py` 的 Cb/Cr 投影雏形，扩展为同时拟合增益 ramp。）
2. **tone{H/S/M/blacks/whites} + contrast → tone/gamma 表**：
   用 Caduceus `ep7_tone_model` 的数学合成目标 gamma，拟合 E-P5 的 tone ramp。
3. **hue[12] / light[12] → 色度曲线非对称 + 增益微调**：
   E-P5 色度曲线可做 Cb/Cr 非对称（近似色相旋转），light 通过 tone 表近似。
   强色相旋转有误差，但常见胶片（Velvia/Portra/Gold）拟合度足够。
4. **wb_shift{a_b,g_m} → 色度曲线中心偏移**（128 中性点偏移）。

**这是「用上 Caduceus 胶片数据」的现实路径，且保留 ISP 原生高画质。**

---

## 4. 阶段 A 的具体做法（用上游数据增厚 7 槽）

1. 写 `tools/caduceus_to_ep5.py`：读 library_v2/v3 配方 → 投影拟合 → 输出每槽的
   {色度曲线 pair, 色度增益 ramp, tone 表}。
2. 定位每槽的增益 ramp / tone 表指针（从 CMIO dispatcher 展开，建 `build/art-gain-tone-map.json`）。
3. 扩展 `build_safe_full.py`：除 pair 外，再写增益 ramp + tone 表（纯数据）。
4. 探针验证：只改目标模式、共享/录像回原厂、效果指针非零。
5. 真机拍同一静物，对比 safe-7，确认色彩丰富度提升。

风险：低（纯数据，RC2 同类）。先做 Velvia/Portra/Gold 三槽验证拟合质量，再扩到 7 槽。
