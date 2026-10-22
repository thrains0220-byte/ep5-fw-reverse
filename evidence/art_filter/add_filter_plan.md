# E-P5 1.8「新增创意滤镜」的完整落点方案

> 日期：2026-10-22（第十一轮）
> 性质：静态观察 + 结构性推断（**未实机验证**）
> 结论摘要：**E-P5 固件实现了 15 个艺术效果，机身菜单只暴露 10 个；
> 另外 4 个（Star Light / White Edge / Pastel / Clear Line）实现与 UI 名字都在，
> 只差"资源 ID + 菜单登记"这一步。**

---

## 1. 固件实现 vs 机身菜单（完整对照）

### 1.1 固件实现的 15 个艺术效果

| 实现 | pass | 编号 | UI 名字在块 1 | 名字偏移 | 菜单资源 ID |
|---|---|---|---|---|---|
| `art_composite` | 4 | — | Pop Art | 0x31971E | **A03F** |
| `art_filter_dramatic_tone` | 12 | NN 14 | Dramatic Tone | 0x34EC56 | **A040** |
| `art_soft_focus` | 6 | ID 40 | Soft Focus | 0x34ECEC | **A041** |
| `art_stl2ycc` | 7 | — | Pale&Light Color | 0x34ECBA | **A042** |
| `art_stl2ycc2` | 3 | — | Light Tone | 0x34ECA4 | **A043** |
| `art_filter_rough_monochrome` | 9 | NN 6 | Grainy Film | 0x34EC8C | **A044** |
| `art_pinhole` | 5 | ID 20 | Pin Hole | 0x2B4176 | **A045** |
| `art_diorama` | 9 | NN 9 | Diorama | 0x2E863E | **A046** |
| `art_mirror` | 2 | — | Cross Process | 0x301038 | **A047** |
| `art_filter_gentle_sepia` | 3 | — | Gentle Sepia | 0x34EC72 | **A048** |
| `art_frame` | 5 | ID 30 | （Frame） | 0x2BC89A | — |
| `art_star_light` | **15** | **ID 10** | **Star Light** | **0x33B7C0** | **无** |
| `art_white_edge` | 5 | ID 50 | **White Edge** | **0x355B42** | **无** |
| `art_pastel_art` | **11** | **NN 21** | **Pastel** | **0x2E92DC** | **无** |
| `art_artclearline` | **13** | **NN 19** | **（无，需新增）** | — | **无** |

### 1.2 机身照片模式菜单（英语分区，块 1 偏移 `0x3543AC–0x3544EE`）

```
@A03F  Pop Art
@A040  Dramatic Tone
@A041  Soft Focus
@A042  Pale&Light Color
@A043  Light Tone
@A044  Grainy Film
@A045  Pin Hole
@A046  Diorama
@A047  Cross Process
@A048  Gentle Sepia
```

**资源 ID 连续、恰好 10 项**，与 1.1 表中"有 ID"的 10 个效果一一对应。

### 1.3 关键结论

> **① 固件里多实现了 5 个效果，其中 4 个（Star Light / White Edge / Pastel / Clear Line）
> 在菜单里完全没有位置。**
> **② 其中 3 个（Star Light / White Edge / Pastel）的 UI 名字字符串已经在块 1 里了**
> （只是没有被任何 `@A0xx@` 菜单项引用）。
> **③ 资源 ID `A04F` 是 A03F–A05F 区间内唯一的空缺**，
> 正好紧接在照片模式菜单 A03F–A048 之后 ⇒ **新增滤镜的现成落点**。

---

## 2. 资源 ID 空间统计

块 1 共使用 **249 个** `@A0xx@` 资源 ID，范围 `A000..A0FA`：

| 区间 | 已用 | 空缺 |
|---|---|---|
| A000–A03E | 全部 | — |
| **A03F–A048** | 10（照片模式菜单） | — |
| **A049–A04E** | 6（其它菜单项） | — |
| **A04F** | — | **★ 唯一空缺（紧邻照片模式菜单）** |
| A050–A0FA | 全部 | — |

---

## 3. 实现"新增一个滤镜"需要改什么

| # | 位置 | 改动 | 数据量 |
|---|---|---|---|
| 1 | **块 1** `A04F` 槽位 | 分配资源 ID 给新滤镜名字（用已有的 `Star Light`/`White Edge`/`Pastel` 字符串，或为 Clear Line 新增） | 1 条菜单项 + 名字 |
| 2 | **块 1** 照片模式菜单表 | 在 `@A03F..@A048` 之后插入 `@A04F<名字>` | 每个语言分区 1 项 |
| 3 | **块 0** 效果 ID → 实现注册表 | 增加新效果 ID 的条目 | 见 §4（待精确测定） |
| 4 | **块 0** 菜单 ID → 效果 ID 对应 | 增加新 ID 的映射 | 待定位 |
| 5 | 容器 | `encode()` 重混淆 + 重算 sum32 + 重打包 | `tools/oly_container.py` 的 `replace_payload()` 已具备 |

**块 1 的大小是固定的**（E-P5 = 22,937,536 B），因此步骤 1、2 需要在块 1 内**复用已有空白区**
或**等长替换**。块 1 的内部布局（语言分区边界、字体区、字符串池对齐规则）需先解析清楚
（见 `docs/PROJECT_STATUS.md` §7 缺口表）。

---

## 4. 仍然待精确测定的两处

| # | 待测定 | 现状 | 手段 |
|---|---|---|---|
| 1 | **效果 ID → 实现函数**注册表 | 效果 ID 全局 `0x605FCD3C` 的 9 处引用全在 `0x4078844C–0x40789522`（艺术簇），但只比较了 ID 10 与 50 | 在 83 函数的艺术簇里找对 20/30/40 的分派；比较可能是 `ID/10` 的索引表 |
| 2 | **菜单资源 ID → 效果 ID** 对应 | 已知块 1 用 `@A03F..@A048`；块 0 内有连续 u16 资源 ID 索引表（file 0x34F542 等） | 把块 0 索引表与块 1 菜单项对齐 |

---

## 5. 一个必须诚实说明的观察

**`art_*` 字符串在块 0 里零代码引用。** 这经 Ghidra 全量指令级扫描确认
（`Mn103ArtImplMap.java`，10,626 个候选字符串、6.49M 条指令，命中 0）。
因此：

- 它们**不能**用来定位实现代码 ⇒ 效果实现不按名字分派；
- 它们是一份**残留的符号名表**（可能是带 trace 设施的构建产物），
  但**忠实记录了该机型的效果集合与编号** ⇒ 作为**逆向成果的目录**极有价值。

---

## 6. 复现

```sh
# 块 1 的菜单资源 ID 表 + 目标名字覆盖情况
python tools/block1_menu.py
python tools/block1_filter_names.py

# 固件侧 15 个效果实现
python tools/art_effects_numbered.py
```
