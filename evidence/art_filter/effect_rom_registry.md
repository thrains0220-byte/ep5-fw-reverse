# E-P5 1.8「效果 / 处理模式」注册表 —— 图像引擎侧的 20 槽 ROM 表

> 日期：2026-10-22（第十二轮）
> 性质：静态观察
> 地位：这是**滤镜链路的最后一环**——它把机身菜单的 10 个照片模式
> 映射到机身 ROM 里的 9 个效果参数块。

---

## 0. 完整链路（本次拼合完成）

```
机身菜单（块 1）        块 0 艺术层                块 0 图像引擎层            机身 mask ROM
@A03F..@A048  ──►  效果 ID 10/20/30/40/50  ──►  20 槽 ROM 参数块表  ──►  9 个效果参数块
（10 个照片模式）        (0x605FCD3C)              (0x40A56338)              (0x7E5C9xxx)
```

---

## 1. 20 槽位 / 9 个不同 ROM 参数块的表

**位置**：运行时 `0x40A56338`（块 0 文件内偏移 `0x796338`）
**上下文**：紧跟在 `0x7E5C86DB`（×6）与 ASCII 串 `"x-bt/img-"` 之后
⇒ 属于**图像处理引擎（img-）**的资源表区。

```
槽  0: 0x7E5C9171      槽 10: 0x7E5C9142
槽  1: 0x7E5C9194 ★    槽 11: 0x7E5C9185
槽  2: 0x7E5C913E      槽 12: 0x7E5C9194 ★
槽  3: 0x7E5C918F      槽 13: 0x7E5C9194 ★
槽  4: 0x7E5C9194 ★    槽 14: 0x7E5C9146
槽  5: 0x7E5C9194 ★    槽 15: 0x7E5C9194 ★
槽  6: 0x7E5C9194 ★    槽 16: 0x7E5C9194 ★
槽  7: 0x7E5C9169      槽 17: 0x7E5C918A
槽  8: 0x7E5C9194 ★    槽 18: 0x7E5C916D
槽  9: 0x7E5C9194 ★    槽 19: 0x7E5C9194 ★
```

- **20 个槽位**，分为前后各 10 个
- **9 个不同的 ROM 参数块**
- `0x7E5C9194` 出现 **11 次** ⇒ **默认/无效果** 的占位项

---

## 2. 与菜单、艺术实现的对应

| 槽位段 | 数量 | 对应 |
|---|---|---|
| 槽 0–9 | 10 | 机身照片模式菜单 `@A03F..@A048`（10 项） |
| 槽 10–19 | 10 | **推测**：同模式的**录像**形态参数 |

9 个非默认块与已逆向出的效果实现数量吻合：

| 菜单项 | 资源 ID | 固件实现 |
|---|---|---|
| Pop Art | A03F | `art_composite` |
| Dramatic Tone | A040 | `art_filter_dramatic_tone` |
| Soft Focus | A041 | `art_soft_focus` |
| Pale&Light Color | A042 | `art_stl2ycc` |
| Light Tone | A043 | `art_stl2ycc2` |
| Grainy Film | A044 | `art_filter_rough_monochrome` |
| Pin Hole | A045 | `art_pinhole` |
| Diorama | A046 | `art_diorama` |
| Cross Process | A047 | `art_mirror` |
| Gentle Sepia | A048 | `art_filter_gentle_sepia` |

⇒ **菜单 10 项 ↔ 艺术层 10 个效果实现 ↔ 图像引擎 20 槽（10 照片 + 10 录像）**。

而**未进入菜单的 4 个已实现效果**
（`art_star_light` / `art_white_edge` / `art_pastel_art` / `art_artclearline`）
在图像引擎表里也**没有对应槽位** ⇒ 它们的参数块不在这个表里。

---

## 3. 艺术簇内引用的其它 ROM 地址

块 0 艺术簇（`0x40788300–0x40789600`）共引用 8 个 `0x7E5C9xxx` ROM 地址：

| ROM 地址 | 引用位置（file） | 角色 |
|---|---|---|
| `0x7E5C9809` | `0x4C862C` | **拍照**效果参数源（`FUN_40788616` 的 t==2 分支） |
| `0x7E5C9B1C` | `0x4C863F` | **录像**效果参数源（`FUN_40788616` 的 else 分支） |
| `0x7E5C9D1E` | `0x4C9235` | 效果参数区查询（`art_get_*_addr` 类） |
| `0x7E5C9E0E` | `0x4C929E` | 同上 |
| `0x7E5CA4EC` | `0x4C930D` | 同上 |
| `0x7E5CA6E7` | `0x4C96A7` | 同上 |
| `0x7E5CA71B` | `0x4C9643` | 同上 |
| `0x7E5CA74F` | `0x4C964F` | 同上 |

⇒ 艺术层通过 **6 个额外的 ROM 地址** 取各效果的参数区；
这 6 个很可能对应 **`art_get_dramatic_tone_addr` 之类的按效果取地址的查询**。

---

## 4. 由此得到的、修正后的可行性结论

| 目标 | 结论 | 原因 |
|---|---|---|
| **解锁 4 个未暴露效果的录像形态** | ✅ 可行 | 艺术层的录像分支（`FUN_40788616` else 分支 / `FUN_40788A5B` 默认分支）只差几个字节 |
| **把 4 个未暴露效果挂到照片模式菜单** | ⚠️ **部分可行** | 名字已在块 1（Star Light / White Edge / Pastel），资源 ID `A04F` 空闲，**但图像引擎 20 槽表里没有它们的槽位** ⇒ 还需要在 `0x40A56338` 表里加槽（表在**块 0**内，**可改**），且需要为它们准备 ROM 参数块（**ROM 不可改** ⇒ 只能指向已有的 9 个块之一） |
| **创造一个全新滤镜（不同像素效果）** | ❌ 不可行 | 效果参数块在机身 mask ROM，固件改不了 |
| **给已有滤镜换参数变体** | ✅ 可行 | 效果 50 = 效果 10 + 312 字节参数覆盖（`0x605FCE7C → 0x605FCD44`） |

> **⇒ 最现实、收益最高的路线**：**解锁现有 10 项的录像形态**，
> 以及**把 `art_star_light` / `art_white_edge` / `art_pastel_art` 挂进菜单并指向已有 ROM 块**。
> 全新算法则受限于 mask ROM。

---

## 5. 仍然待测定的三处

| # | 待测定 | 手段 |
|---|---|---|
| 1 | 9 个 ROM 块 ↔ 10 个菜单项的**一一对应** | 逐个反编译 `art_get_*_addr`（6 个 ROM 地址的查询点），或用 E-M5 II / E-M1X 同位置对照 |
| 2 | 20 槽表的**消费者**（谁按槽索引） | 该表无直接地址引用（经结构体基址 + 索引访问）；在 Ghidra 里从 img- 区域反向追 |
| 3 | 4 个未暴露效果在 ROM 里**是否已有参数块** | 实机 dump mask ROM，或找 E-M5 II（该代可能有更多效果）对照 |

---

## 6. 顺带确认：REA 分析 MN103 的能力边界

尝试用 REA 直接分析 E-P5 块 0 的结论：

| 尝试 | 结果 |
|---|---|
| `open_binary(<decoded.bin>)` | ✗ `unsupported binary format`（裸 .bin 不被识别） |
| `open_binary(<64KB slice>, format="dos-com")` | ⚠️ 能打开，但 `architecture: x86` —— REA 的 dos-com 路径在 `dist/ghidra/GhidraLoadImageValues.js` 里**硬编码** `x86:LE:16:Real Mode`，`REA_GHIDRA_LANGUAGE_ID` 覆盖对 dos-com 不生效 |
| `REA_GHIDRA_LANGUAGE_ID=MN103:LE:16:default` 覆盖 | 已通过 `mcp update` 写入 MCP server 配置（`envKeys` 确认），但**需 server 重启**才生效 |
| Ghidra 12.1.4 的 ELF→语言映射 | 安装树内**没有任何 `*.elfspec`**，故无法让 Ghidra 的 ELF 加载器识别 MN103 |

⇒ **结论：MN103 固件的分析目前只能走 headless Ghidra**（`analyzeHeadless` + 自写 SLEIGH 脚本），
REA 在本项目中的定位是**证据管理 / 归档 / 固件容器与 PE 资源层面**（Binwalk/Unblob 已在用）。
这是**如实记录的能力边界**，不是回避。

---

## 7. 复现

```sh
# 图像引擎 20 槽 ROM 表
python tools/find_rom_effect_table.py decoded/00_0100_402c0020.decoded.bin 0x402C0000 0x7E5C9
```
