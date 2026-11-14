# 阶段 A：用 Caduceus 配方数据增厚 ART 胶片色彩（2026-11-14）

## 目标
safe-7 已真机验收，但用户反馈"借 ART 实现的胶片色彩丰富度不够"。本轮**只做阶段 A**：
提高现有 7 个 ART 槽的色彩丰富度，不碰 P/A/S/M 挡位，不碰共享增益/tone 表。

## 做了什么
把两个上游项目的**数据**（不是固件代码）接进 E-P5 的安全 pair 机制：

1. **配方数据** `build/research/caduceus-ep7-main/sim/recipes/library_v2.json`
   每个 look 的 12 扇区 `sat/hue/light`（−7..7）+ `wb_shift`。用了 6 个彩色配方：
   Velvia / Portra400 / Gold200 / Cl.Chrome / Ektar100 / CineStill800。
2. **色彩引擎数学** `sim/pipeline.py` 的 `ColorEngine`：raised-cosine 扇区权重、
   `sat_mult = 1 + (w·coeff)/1000`、色相旋转。WB 偏移改在 RGB 域做（物理正确的通道增益）。
3. **实测扇区增益** `build/research/oly_fw_analysis-main/tests/fixtures/color-builder-reference.json`
   PEN-F 真机预测的 12 扇区饱和增益（yellow +5→225/−5→360，yellow-green +5→399…）。
   **这是实测值，不是猜的。**

扇区几何用真实 BT.601 色相锚定（yellow/red/magenta/blue/cyan/green 六个主/副色钉住
UI 索引 0/3/4/6/8/10，中间扇区圆弧插值），避免均匀 30° 在红/品红区的 ~28° 偏差。

## 新工具
- `tools/caduceus_to_ep5.py`：配方 → E-P5 49 字节 Cb/Cr pair（9 节点，加权最小二乘拟合，
  中性 128 锚定，色度加权）。`--all` 出 7 槽，`--recipe X --preview` 单配方误差报告。
- `tools/preview_caduceus.py`：同一底图并排渲染 safe-7 旧曲线 vs 新曲线（仅色度近似，
  不含暗角/模糊等空间效果）。产物 `build/caduceus-fit/preview.png`。
- `tests/test_caduceus_to_ep5.py`：6 项测试（几何锚定/实测增益/中性锚点/打包往返/
  Velvia 增饱和/Portra 降饱和）。

## 拟合质量（25³ sRGB 网格，色度加权）
| 槽 | 配方 | 平均误差/255 | 加权最大 | <10 占比 |
|---|---|---|---|---|
| 人像柔暖 | Portra400 | 2.45 | 4.33 | 96.2% |
| 胶片色彩 | Velvia | 4.78 | 9.11 | 66.0% |
| 经典铬 | Cl.Chrome | 5.63 | 10.19 | 61.2% |
| 柯达金 | Gold200 | 3.24 | 5.74 | 90.0% |
| 风景鲜艳 | Ektar100 | 2.66 | 6.01 | 86.5% |
| 电影色调 | CineStill800 | 5.63 | 9.73 | 60.2% |

误差是"1D 色度投影 vs 完整 12 扇区引擎"的差，丢失的是色相旋转/亮度曲线/分离调色
（这些本就无法用 pair 表达）。色彩取向（增/降饱和、冷暖、非对称）完整保留。

## 相对 safe-7 的"增厚"证据（±64 色度偏差处的增益）
| 槽 | safe-7 Cb 低/高 | 新 Cb 低/高 | safe-7 Cr 低/高 | 新 Cr 低/高 |
|---|---|---|---|---|
| Velvia | 1.19/1.28 | **1.33/1.38** | 1.22/1.34 | 1.23/1.23 |
| Portra | 1.12/1.06 | **0.95/0.86** | 1.09/1.09 | **0.75/0.92** |
| Gold | 1.16/1.12 | 1.22/0.84 | 1.09/1.22 | 0.80/1.00 |
| Cl.Chrome | 1.06/0.97 | **0.78/0.66** | 1.09/0.94 | 0.84/0.94 |
| Ektar | 1.28/1.41 | 1.11/1.20 | 1.31/1.47 | 1.08/1.16 |
| CineStill | 1.25/1.38 | 0.84/1.09 | 1.06/0.91 | 1.11/1.03 |

要点：Velvia 更浓（1.38×）；Portra 真正降饱和且 Cb/Cr 非对称（暖调）；Cl.Chrome 强去饱和
（0.66×，纪实灰调）。safe-7 的 Portra 其实是增饱和（1.12×），方向就错了——本轮修正。

## 候选固件
- 产物 `build/film-caduceus-7/DCOLYMP/E1089999.BIN`
- SHA-256 `d8ae7a20ea48ff7b0c2849ca835fb2899730c811378fb7a82625fab8193bb3bd`
- 44,826,624 字节，与官方整包同尺寸。
- 构建：`python tools/build_safe_full.py data/ep5-stock/OLY_E_108_1800_0000_0000.BIN --out build/film-caduceus-7 --looks build/caduceus-fit/caduceus_looks.json`

## 安全证据（防砖）
1. **机制与 safe-7 完全相同**：只改 pair + 共享/录像隔离 + 菜单改名，效果指针全保留。
2. **逐字节探针**：新固件 vs 已验证 safe-7（SHA 053abcb9…）的全部差异**只**落在 6 个彩色
   pair 的 98 字节区域内（29 段差异，全部命中）。语言块(0x101)/录像块(0x106)/扩展块(0x104)
   字节一致；黑白 pair 一致；共享增益/tone 表(0x7e453xxx)未触碰。
3. **回归**：36 项原有测试 + 6 项新测试全过。
4. 容器往返、原字节匹配、不重叠校验由 `build_update` 强制。

风险等级 = safe-7（已真机启动、成片、官方恢复）。**但新曲线尚未真机实拍**，
状态仍标 `hardware-functional-candidate`，需真机验收后才算完成。

## 刷机步骤（真机验收）
1. 相机关机，SD 卡留机内，电池充足。USB 接电脑选 **Storage/存储**。
2. 把 `build/film-caduceus-7/DCOLYMP/E1089999.BIN` 拷到卡上 `DCOLYMP/`（覆盖旧包）。
3. Windows 安全弹出，拔 USB，关机。
4. **按住 OK 开机**：AF 灯常亮 → 均匀快闪（约每秒 2 次）→ 熄灭。快闪期间不断电不取卡。
5. 灯灭后正常 OFF，等 5 秒，正常 ON。进 ART 确认 7 槽名称与出图。
6. 同一静物拍 RAW+JPEG（4:3、最大、ISO200、固定 WB），对比 safe-7 旧片。
7. 如需回退：刷官方 `data/ep5-stock/OLY_E_108_1800_0000_0000.BIN`（已验证恢复路径）。

## 下一步（阶段 A 收尾后）
- 真机验收新曲线，按实拍微调 `SAT_SCALE`/`WB_*` 标定常数（目前是上游预览标定，非 E-P5 实测）。
- 若用户要更多风格：`library_v3.json` 还有 15 个配方（Kodachrome25/Polaroid/CineStill50D…），
  同一转换器即可产出，受 7 槽数量限制需做替换选择。
- 阶段 B+（P/A/S/M 挡位、SD 热换 LUT）按 `EP5_FILM_SIM_IMPLEMENTATION_PLAN.md` 另行推进。
