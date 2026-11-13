# E-P5 1.8 胶片色彩全量包（7槽·无暗角·HQ 9节点）

## 交付物

`build/ep5-full-7-kit/`：
- `E-P5-1.8-Film-FULL-7.zip` — 7 种胶片色彩，6 个 ART 菜单改名
- `E-P5-1.8-STOCK-RECOVERY.zip` — 官方 1.8 恢复包

固件 SHA-256：`836ff1457a19eb1439205c641ffdc66713a4fd4858752f75aa34023cbb5a57dd`

## 机内体验

ART 模式转盘下，6 个条目改名、7 种独立色彩：

| 菜单名 | 原条目 | 风格 | 取向 |
| --- | --- | --- | --- |
| 人像柔暖 | 柔焦效果 | Portra 400 | 人像肤色暖调、低饱和 |
| 胶片色彩 I | 针孔相机 I | Velvia 50 | 浓艳反转、风景高饱和 |
| 胶片色彩 II | 针孔相机 II | Classic Chrome | 纪实低饱和、微冷 |
| 胶片色彩 III | 针孔相机 III | Gold 200 | 暖金负片、日常 |
| 风景鲜艳 | 立体效果 | Ektar 100 | 风景负片、鲜艳细腻 |
| 电影色调 | 浓郁色调效果 | CineStill 800T | 电影钨丝灯、冷调高光 |
| 森山黑白 | 负片冲印效果 | Moriyama B&W | 纯去色黑白 |

针孔 I/II/III 是选中"胶片色彩"后按**右方向键**切换的子变体。

## 机制

- **效果中性化**：13 处 MOV 立即数清零，所有 ART 槽只排 RAW→YC，不排任何空间/染色效果。无暗角、无模糊、无 sepia、无星芒、无镜像。
- **HQ 9 节点非线性色度曲线**：利用硬件 16 个 x 位置中的 9 个做分段饱和（阴影去饱和/中间调增强/高光保护）。
- **共享/录像隔离**：7 个共享模式全部重路由到模式 72（gate=1 不可达、恒等表）的原厂 case。CMIO 第二轴字面副本指向 72 表族。录像保持原厂色彩。
- **纯数据补丁**：无新增可执行代码、无 cave、无 RAM 控制。风险与已真机验证的 RC2 相同。

## 校验

```bash
# WSL：写入器隔离（7 照片模式变化，7 共享模式回原厂，其余 240+ 不变）
PYTHONPATH=. python3 tools/film_pack/verify_full.py
# WSL：完整拍摄路径（7槽×3录像状态=21组，全幅分配/JPEG/转换器/驱动字）
PYTHONPATH=. python3 tools/film_pack/verify_full_route.py
# Windows：回归
python -m unittest tests.test_native_film_pack tests.test_build_native_film tests.test_film_update
```

三项全过（23 项回归 + 写入器 + 21 组路由）。

## 能力边界

色度曲线能表达：饱和缩放、微偏色、完全去色。9 节点非线性允许按亮度区间分段控制饱和。

不能表达：色相旋转（红→橙）、亮度 S 曲线（高反差）、颗粒、暗角（已去除）。
黑白为纯去色；高反差请用机身对比度设置补足。

任意 3D `.cube` 直出仍走 SD LUT 运行时主线（cave 代码），与本包是两条路。

## 状态

`hardware-functional-candidate`。机制与隔离经探针证明，**未在相机实拍**。
刷入后预期：ART 菜单显示新名称，无暗角/模糊，只有胶片色彩取向。
取景预览可能仍显示原厂效果（预览路径未验证），最终 JPEG 以色度曲线为准。

## 复现

```bash
python tools/build_full_film.py data/ep5-stock/OLY_E_108_1800_0000_0000.BIN --out build/film-full-7
python tools/build_full_film_kit.py data/ep5-stock/OLY_E_108_1800_0000_0000.BIN --out build/ep5-full-7-kit
```
