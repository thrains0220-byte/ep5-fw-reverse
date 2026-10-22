# 外部逆向项目调研笔记（GitHub 公开仓库）

> 日期：2026-10-22（第十四轮汇总）
> 性质：**外部资料转述**，不是本项目的观察结果。
> 用途：为 E-P5 的后续逆向提供跨机型对照与「别人已经踩过的坑」清单。
> 检索方式：子代理用 GitHub 公开 API 拉取仓库树与文件原文（未 clone 进本仓库工作区）。
> 凡与本项目观察冲突之处，以本项目 `evidence/` 下的实证为准，并已在 §5 标注。

---

## 1. `cmdada/em10-fw` —— E-M10（E-M5 同代）

### 1.1 艺术滤镜 ID 体系（最关键的一条）

| 结论 | 内容 |
|---|---|
| ID 空间 | 艺术滤镜 ID = **图像处理器的 mode hash**，落在 `100`–`120+`，并另有 `+1000` 的一组 |
| 名字来源 | 固件自带 **`color_tone` 命令**给出名字，**不是**编译期表 |
| 已见对应 | `100 POPART` … `119 LIGNE_CLAIR`、`120 PASTEL` |

**与 E-P5 的对照（本项目观察）**：
E-P5 固件里 `color_tone` 相关字符串确实存在（`COLORTONE_<name>` 定宽表，见
`evidence/art_filter/art_filter_menu_and_ids.md` §2.2），且 **`LIGNE_CLAIR` / `PASTEL`
正好是 E-P5 那张 12 项 `COLORTONE` 表的最后两项**。
⇒ **推断**：E-M10 的 `100..120` 与 E-P5 的 `COLORTONE` 12 项表**很可能是同一个枚举的不同视角**
（E-P5 侧看不到数字 ID，E-M10 侧能看到）。
但 E-P5 的 `COLORTONE` 表只有 12 项，E-M10 的 ID 段跨 `100..120`（21 项），
**两者不是同一张表**。映射关系未建立 —— 仍未知。

### 1.2 菜单结构

| 结论 | 内容 |
|---|---|
| Picture Mode 菜单 | **21 个取值**，其中艺术滤镜占 `8`–`0x13`（8 位下标区） |
| "show this mode" 开关表 | **21 项**（每个 Picture Mode 一个显隐开关） |

**与 E-P5 的对照**：本项目在 E-P5 块 1 里找到的是**资源 ID 段**（照片 `A03F`–`A048` 连续 10 项），
**不是** 21 项下标表。⇒ E-P5 的 Picture Mode 组织方式与 E-M10 不同，
**E-M10 的地址模板不能直接套用**（这正是本轮待办②的结论）。

### 1.3 自动对焦

- **约 12 组每镜头 AF 参数块**。
- 本项目在 E-P5 侧独立发现 `FUN_4048B6D2` 使用结构体 `+0x46C` / `+0x48C`
  的**每镜头标定表**，按 `*(byte*)(*obj + 8) * 0x10` **16 字节步长**查表
  （`evidence/art_filter/art_filter_address_map.md` §6）。
  ⇒ **两侧"每镜头参数"的数量级吻合**，AF 修复的落点方向可信。

### 1.4 其它

- `notes/menu.md` / `notes/plugins.md` / `notes/autofocus.md`
- `tools/patch.py`（现成补丁框架）
- `openkernel/config/camera_config.h`

---

## 2. `fishcu/oly_fw_analysis`

| 文件 | 内容 |
|---|---|
| `provenance/firmware-inventory.json` | 固件清单；含 **E-PL5 = E-P5 v1.6 的分量表** |
| `provenance/historical-patches.json` | 历史补丁清单 |
| `tools/penf_historical_diff.py` | PEN-F 历史版本差分工具 |
| `docs/features/HISTORICAL_HACKS.md` | 历史 hack 汇总 |

**用途**：E-PL5 与 E-P5 同为 v1.6 ⇒ 该分量表可用来**交叉校验本项目的容器解析结果**
（块数、每块长度、加载地址）。

---

## 3. `sympho-ru/olympus-e-pl3-research`

- E-PL3 与 E-P5 **同代同构**（同为 E-M5 平台）。
- 该项目已把 **block 2 的 6-bit 编码**一路查到排除到底，
  社区项目 "olycompress" 也未能解开。
- ⇒ **本项目"块 2 6-bit 未解"不是本项目的短板**，是该代机型的公开盲区。
  **不应在这条线上继续投入**（成本高、公开先例均为负）。

---

## 4. `nivag8899/olympus-em1m3-research`

- E-M1 Mark III 研究。与 E-M5 平台无关（更老一代），
  仅作 Olympus 固件工程习惯的横向参考。

---

## 5. 跨仓库对照结论表

| 主题 | 外部资料 | 本项目观察（E-P5） | 一致性 |
|---|---|---|---|
| 艺术滤镜 ID | E-M10：`100`–`120` mode hash | E-P5：两套命名空间 `10/20/30/40/50` 与 `06/09/0E/14/19/1C/1D/21` | **不一致** ⇒ 至少两代、两套编号体系并存 |
| 滤镜名字来源 | E-M10：`color_tone` 命令 | E-P5：固件内 `COLORTONE_<name>` 定宽表（12 项） | 一致（E-P5 有同名表） |
| 每镜头参数 | ~12 组 | `FUN_4048B6D2` + 16B 步长查表 | 一致 |
| Picture Mode 组织 | 21 项下标 + 21 项开关表 | 资源 ID 段 `A03F`–`A048`（10 项）+ 录像 4 项 | **不一致** ⇒ 不能套用 E-M10 地址模板 |
| block2 6-bit | 未解（社区亦未解） | 未解 | 一致（公开盲区） |

---

## 6. 对后续工作的三条指令

1. **不要再在 block2 的 6-bit 编码上投入**（公开先例全负）。
2. **不要照搬 E-M10 的 Picture Mode 地址模板**去 E-P5 搜 —— 结构不同（已实证）。
3. **优先做实机 mask ROM dump**：`0x7E000000`–`0x7FFFFFFF` 区段是所有"菜单项组成 /
   滤镜调校参数"的唯一存放处；没有它，"新增菜单项 / 新增滤镜"两条路都封死在门外。
