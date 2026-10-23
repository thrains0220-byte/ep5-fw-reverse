# 项目现状总表（E-P5 固件逆向）

> 更新：2026-10-23（第十七轮：松下 AF 修复官方矩阵 / **地面真值差分对** / **镜头 ID 链证伪** / OMSRV 接口现状）
> 第十六轮：容器两层结构 / 每块构建时间戳 / 六比特层不变性 / E-M10 II 新差分对
> 仓库：[thrains0220-byte/ep5-fw-reverse](https://github.com/thrains0220-byte/ep5-fw-reverse)（公开）
> 主报告：[`report/逆向分析报告_E-P5_Ver1.8.md`](../report/逆向分析报告_E-P5_Ver1.8.md)
> 方法论：[`RE_METHOD_PLAYBOOK.md`](RE_METHOD_PLAYBOOK.md)

---

## 1. 项目目标

| # | 目标 | 状态 | 备注 |
|---|---|---|---|
| A | 破解 E-P5 1.8 固件容器格式 | ✅ **完成** | 100% 破解，往返逐字节一致 |
| B | 定位 2018-12-18 松下镜头 AF 修复的补丁字节 | ⚠️ **落点再收窄（第十七轮）** | 修复**不在**镜头 ID 结构；**第十七轮新增地面真值**：E-PM2 v1.5→v1.6、E-M5 v2.2→v2.3 是**已确认含修复**的差分对 →（a）非代码分区**逐字节完全相同**；（b）**镜头 ID 比较链修复前后完全一致** ⇒ 上一轮"补丁=0xC0F1/0xC0E1"**被证伪**；（c）全固件唯一签名 = `fcs_lens_mfts_move_lens_ofset_target` 被移除 ⇒ 落点在 **`fcs_lens_mfts` 镜头 AF 驱动模块**内 |
| C | 定位艺术（创意）滤镜实现 | ✅ **实现位置与数据流已破解** | 完整地址地图见 `evidence/art_filter/art_filter_address_map.md`；ID 空间与菜单映射见 `art_filter_menu_and_ids.md` |
| D | 定位"解锁录像艺术滤镜"的落点 | ✅ **代码层 3 处 + 资源层 1 处已定位** | 位掩码 `0x602AEB94` / 分支判定 / 各效果类型白名单；**资源层：录像菜单只有 4 项 vs 照片 10 项** |
| E | 做出"新增创意滤镜"的固件补丁 | 🔶 **方案已定型，未实施** | 模板 A（参数覆盖式）已由伪代码证实可行 |
| F | 实机刷写验证 | ❌ **未做** | 无 E-P5 实机 |
| G | 块 2 的 6-bit 编码 | ⛔ **本轮定性：不可用统计法解码** | 该层在**已检查的全部 30 个固件（0 未命中，跨 2012–2022、8 个机型族）**中**逐字节恒定**（SHA-256 `93c4e55881cd…`）⇒ **不可能承载任何版本差异**；且无残余类结构、无自相关，差分/频率/对齐三法全部失效。解码器疑在 mask ROM ⇒ 见 `evidence/fw_layout/round16_container_layout_and_blk106.md` |
| H | 机身侧镜头 ID ↔ 镜头型号对照表 | ❌ 公开世界不存在 | 已全量检索确认 |

---

## 2. 已确立的事实（观察级，均有可复现证据）

### 2.1 容器与校验

| 项 | 值 |
|---|---|
| 容器 | "OE"/"OM" 混淆块容器，4 块 ×（32B 头 + payload + 32B 尾） |
| 混淆 | 16 字节内 16 列字节置换 + 全字节 XOR 0xFF |
| 置换 | `DECODE_ORDER = (1,3,0,2,6,4,7,5,11,10,9,8,13,14,12,15)` |
| 校验 | **加法 sum32**（`-Σ(u32 LE)`），非 CRC |
| 往返 | `decode → encode` 与源文件 SHA-256 **完全相同** |
| 补丁 | `replace_payload()` 可改 payload 并**自动重算**尾校验和 |

> ⚠️ **地址约定更正（第十六轮，观察级）**
> 本项目历史坐标（块 0 基址 `0x402C0000`）比容器规范换算**低 0x20**。
> 规范换算为 `运行地址 = header_address + 0x20 + payload_offset`（= `container_payload_address + payload_offset`），
> 依据：① `tools/oly_container.py` 与 `decoded/manifest.json` 的 `container_payload_address` 字段；
> ② 块 2 的**自述地址** `payload[4:8] = 0x43DA0400` 恰好等于 `0x43DA0020 + 0x3E0`（数据区实际起点），
> 而旧换算会得到 `0x43DA03E0`（差 0x20）。
> 更正后 E-P5 1.8 关键坐标：镜头链函数 `0x403B79A9`、链内 ROM 指针 `0x403B7A2B`、
> 白名单字 `0x403B7A47`、LENS_INFO 主表 `0x405E8F00`。
> 详见 `evidence/fw_layout/round16_container_layout_and_blk106.md` §7。

### 2.2 指令集与工具链

| 项 | 值 |
|---|---|
| 指令集 | Panasonic MN1030 / MN103S，16 位小端 RISC |
| 反汇编 | 自建 binutils 2.45 `--target=mn10300-elf`；**Ghidra + 第三方 SLEIGH 模块**（本项目主力） |
| 一致性验证 | Ghidra vs objdump：窗口 77/77 指令逐条一致，0 差异 |
| 规模 | 块 0 15,728,576 B → 6,488,149 条指令 / **56,984 个函数** / 约 60 s |
| Ghidra 补丁 | `mn103-call.patch`（`call f,[regs],imm` 保存寄存器恢复）+ `mn103-olympus.cspec`（Olympus 调用约定） |

### 2.3 镜头子系统

| 项 | 地址/值 |
|---|---|
| LENS_INFO 镜头主表 | 块 0 `0x405E8EE0`，**106 条 8 字节记录 / 105 个唯一镜头 ID** |
| 记录格式 | `{uint16 category, uint16 slot, uint8 maker, uint8 model, uint16 extra}` |
| 厂商码 | `60 70 80 81 B0 B1 C0 C1 C2 C3 D0 D1 E0`（13 组） |
| 镜头 ID 前缀比较链 | E-P5 `0x403B7989` 7 对；E-P3 `0x403EFBC5` 4 对；E-M5 v2.2/v2.3 均 7 对 |
| 链函数中的 mask ROM 指针 | E-P5 1.8 `0x403B7A0B` = `mov 0x7E43018C,a0`；E-PM2 v1.5 `0x7E741BFC` → v1.6 `0x7E741EA8`；E-M5 v2.2 `0x7E8766A6` → v2.3 `0x7E876968` |
| mask ROM 映像位移（修复版） | E-PM2 **+0x2AC / +0x288**；E-M5 **+0x2C0 / +0x298** ⇒ ROM 映像被扩充 |
| 每镜头标定表 | 结构体 `+0x46C` / `+0x48C`，16 字节步长（`FUN_4048B6D2` = 镜头畸变校正） |
| LENS_INFO 结构字段表 | **固件自带调试转储**，完整列出 20 个子结构（`LENS_INFO_AF_CON` / `_IS` / `_LAF` / `_AF` / `_DIST` / `_DISTORTION` / `_SHADING` / `_MAKERNOTE` / `_FOURTHIRDS` / `_EZ` / `_PRIVATE` / `_LENS_OIS` / `_ENABLE` / `_CHARACTER(_ZM)` / `_STATE` / `_ALL_DATA` / `_CURRENT_CONSUMPTION` / `_RESERVED`），见 `evidence/af_fix_2018/lens_info_af_layout.md` |
| 每镜头 AF 参数挂载点 | `LENS_INFO_LAF.af_data_pos[%d]`（格式串 @ `0x405ED07B`）；**数据本体在 mask ROM** ⇒ 固件补丁不可改写 |

### 2.4 艺术（创意）滤镜子系统 ★

**固件实现了 15 个艺术效果，机身菜单只暴露了一部分** —— 这是"新增滤镜"最关键的发现。

| 实现 | pass | 编号 | 首现 |
|---|---|---|---|
| `art_star_light` | 15 | ID 10 | 0x454F0D |
| `art_artclearline` | 13 | NN 19 | 0x457FBF |
| `art_filter_dramatic_tone` | 12 | NN 14 | 0x457738 |
| `art_pastel_art` | 11 | NN 21 | 0x458AAD |
| `art_diorama` | 9 | NN 9 | 0x456EF6 |
| `art_filter_rough_monochrome` | 9 | NN 6 | 0x4567B3 |
| `art_stl2ycc` | 7 | — | 0x45A8A8 |
| `art_soft_focus` | 6 | ID 40 | 0x455F35 |
| `art_frame` | 5 | ID 30 | 0x45589C |
| `art_pinhole` | 5 | ID 20 | 0x4555C6 |
| `art_white_edge` | 5 | ID 50 | 0x456311 |
| `art_composite` | 4 | — | 0x458794 |
| `art_filter_gentle_sepia` | 3 | — | 0x4573BB |
| `art_stl2ycc2` | 3 | — | 0x45A948 |
| `art_mirror` | 2 | — | 0x458611 |

**已实现但未在照片模式菜单出现的**：`art_artclearline`（净化直线）、
`art_star_light`（星光）、`art_pastel_art`（粉彩）—— 三个都是 10+ pass 的完整管线。

> ⚠️ **第十四轮修正**：上表的"15 个效果"是按**函数名簇**统计的；
> 按**编译单元**统计，E-P5 的艺术滤镜实现为 **13 个模块**（见 §2.6）。
> 且"菜单里没有名字"不等于"实现里没接线"——§2.6 证明录像菜单**只有 4 项**，
> 差 6 项的字符串在块 1 里**已经存在**，只是没被录像菜单引用。

| 语义 | 地址 |
|---|---|
| 效果 ID 全局 | `0x605FCD3C`（9 处引用全在 `0x4078844C–0x40789522`） |
| 效果类型全局（拍照/录像） | `0x605FCD40`（值 2 = 拍照） |
| 支持的类型位掩码 | `0x602AEB94` |
| 效果回调指针 | `0x602AEB54` |
| 效果参数区（当前生效） | `0x605FCD44`（312 B） |
| 效果 50 参数模板 | `0x605FCE7C`（312 B，恰好相隔 0x138） |
| 拍照参数区 / 录像参数区 | `0x605FCA00` / `0x605FCCC4` |
| 效果 ID 设置器 / 复位器 | `FUN_407887E0` / `FUN_40789519` |
| 子系统总初始化 | `FUN_407883DD` |
| 按类型初始化 | `FUN_40788616` / `FUN_4078866A` |
| 效果回调派发 | `FUN_40788CAC` |
| 模式分派器 | `FUN_40788978`（模式 `1` / `0x80000000` / 默认拍照） |
| 录像/照片判定 | `FUN_40788A6C`（标志 `0x20000000`） |

**两个新增滤镜模板**：
- **A（参数覆盖式）**：312 B 参数块 + 复用既有效果管线（效果 50 = 效果 10 + 参数覆盖）
- **B（独立式）**：新 ID(60) + 独立参数块 + 独立 pass + 初始化登记

**三个解锁落点**：`0x602AEB94` 位掩码 / `FUN_40788616` 的 `param_1 == 2` 判定 /
各效果初始化函数的类型白名单。

### 2.5 固件子系统全景

`docs/subsystem_map.md`（92 KB）给出块 0 的**完整子系统清单**：

| 类别 | 数量 | 样例 |
|---|---|---|
| 日志标签（子系统锚点） | **752** | `[GUI App]`710 / `[chls]`393 / `[exp]`307 / `[AVCHD]`169 / `[WIFI@]`101 / `[firmup]`84 / `[MOV_ART]`50 / `[exp_debug]`91 / `[disp_sync]`99 |
| `g_*` 全局状态变量 | 16 | `g_lens_speed` / `g_fcs_step` / `g_drive_mode` / `g_contrast_dma_addr` |
| 函数名簇（≥2 段） | **638** | `api_*`1110 / `art_*`752 / `chls_*`290 / `aud_*`110 / `se1_3d_*` / `dbg_cgi_*` |

⇒ 已识别的子系统：GUI/触摸、色彩（chls）、曝光（exp）、录像（AVCHD/MOV/QT/MOOV）、
WLAN+httpd+olnet、音频（aud/wm8946）、固件升级（firmup）、显示（disp/OUT/IN）、
文件分析（analyze/CLIP/chunk）、3D 立体（se1_3d/se2）、GPS、CGI 调试（dbg_cgi_*）、
图像处理 API 与校准（api/api_adj）、IOE、TPC、GPU、AF/镜头、菜单与 OSD。

### 2.5 UI 资源（块 1）

- 块 1 = **UTF-16LE 多语言字符串池**（每条以 UTF-16 NUL 结束），22,937,536 B
- E-P5 照片模式菜单定义（带连续资源 ID）：
  `A03F` Pop Art / `A040` Dramatic Tone / `A041` Soft Focus / `A042` Pale&Light Color /
  `A043` Light Tone / `A044` Grainy Film / `A045` Pin Hole / `A046` Diorama /
  `A047` Cross Process / `A048` Gentle Sepia
- 块 0 内另有 UI 资源 ID 索引表（连续 u16 数组）

> ⚠️ **第十四轮修正**：上表是**精确整串匹配**的结果；
> 第十三轮的 `block1_filter_names.json` 用偏移邻接取值，产生了
> 「A042 同时是 Grainy Film 与 Pale&Light Color」这类**假冲突**。
> 正确做法见 `tools/block1_art_id_map.py`。

### 2.6 艺术滤镜：ID 命名空间 / 菜单映射 / 资源描述符表 ★（第十四轮）

完整证据：[`evidence/art_filter/art_filter_menu_and_ids.md`](../evidence/art_filter/art_filter_menu_and_ids.md)

**（a）两套 ID 命名空间，13 个实现模块**

| 命名空间 | ID | 名字 |
|---|---|---|
| `art_effect_<NN>` | 10 / 20 / 30 / 40 / 50 | star_light / pinhole / frame / soft_focus / white_edge |
| `art_filter_<HH>` | 06 / 09 / 0E / 14 / 19 / 1C / 1D / 21 | rough_monochrome / diorama / gentle_sepia / dramatic_tone / artclearline / mirror / composite / pastel_art |

每个模块都有一个 **`.c` 源文件名字符串**（如 `art_effect_40_soft_focus.c` @ `0x407160EC`），
给出字符串块的精确边界。E-P5 v1.8 与 E-PM2 v1.6 的 ID 完全一致，仅地址平移。

**（b）三张互不相同的滤镜名字集合**

| 集合 | 项数 | 内容 | 位置 |
|---|---|---|---|
| 实现模块名 | 13 | §2.6(a) | 块 0 `0x40714000`–`0x4071B000` |
| `MODE_EXPOSE_*` | 22（+9 场景） | POPART…PASTEL，每项带 `_MOVIE` 孪生 | `mov_art.c` @ `0x406B2000` |
| `COLORTONE_*` | 12（+7 色彩模式） | POPART…PASTEL，**3 份不同顺序**（其中一份是录像侧重排） | 块 0 `0x40AB1143` |

**（c）两张 UI 菜单 —— 锁定点的资源层形态**

| 菜单 | 资源 ID | 项数 | 名字 |
|---|---|---|---|
| 照片艺术菜单 | `A03F`–`A048`（连续） | **10** | Pop Art / Dramatic Tone / Soft Focus / Pale&Light Color / Light Tone / Grainy Film / Pin Hole / Diorama / Cross Process / Gentle Sepia |
| **录像艺术菜单** | `A042`–`A045` | **4** | Grainy Film / Pin Hole / Diorama / Dramatic Tone |

⇒ **录像艺术菜单比照片少 6 项**（Pop Art / Soft Focus / Pale&Light Color / Light Tone /
Cross Process / Gentle Sepia），这 6 项的**多语言字符串在块 1 里已经存在**，只是没被引用。

**（d）块 0 的 UI 字符串资源描述符表（总闸门）**

`rt 0x402D8BEC`（file `0x18BEC`），**28 字节/条，99 条**，
ID `0x36`–`0x92`（连续）+ `0x9D`–`0xA2`，字段
`{u32 id, 0, 0, u32 mask_rom_ptr, u32 type, u32 flags, 0}`。
艺术滤镜段 ID `0x3F`–`0x48` 的描述符在 mask ROM `0x7E2Axxxx`–`0x7E5Cxxxx`。
**`0x93`–`0x9C`（10 个 ID）在表里没有记录。**

> **推断**：菜单项的**组成**很可能在 mask ROM 描述符里 ⇒
> "加菜单项"这条路被 mask ROM 卡住，必须靠实机 dump 确认。

---

### 2.7 容器两层结构 · 每块构建时间戳 · 资源容器（第十六轮新增）

| 项 | 值 |
|---|---|
| 外层「更新容器」 | 32B 头 + payload（**混淆**：16B 组内字节平面转置 + XOR 0xFF）+ 32B 尾；**加法 sum32 校验**在尾 `[28:32]` |
| 内层「运行映像」 | 某些分区 payload 内**又嵌一层容器**：32B 头 + payload（**明文、不混淆、无校验**）+ 32B 尾；`kind=0x0006` |
| **构建时间戳** | 内层块头 `[24:28]` = **Unix 时间戳（UTC）**。E-M10 II v1.3 = 2018-04-11 00:49:04–08；v1.4 = 2018-12-13 02:59:41–53；E-P7 v1.2 = 2018-12-13 09:16:39–54（同日构建批次） |
| 独立佐证 | 代码块内编译器日期串同步变化：`Apr 11 2018` → `Dec 13 2018` |
| `kind 0x106` 分区 | = **资源容器**：内层映像首块带 **40 条 16B 目录** `{u32 运行地址, u32 大小, 0, 0}`；条目 0 就是六比特 blob（0x240000） |
| 资源内容 | E-PM1(1130) 的同一分区含 **14 个完整 JPEG**（4608×3456 / 3456×3456 / 640×480 / 1280×720）⇒ 该分区带原始示例照片 |
| 格式代差 | E-P5 v1.8（2012 代）的 `kind 0x106` **只有 blob**（无目录、无 JPEG）⇒ 该分区在 2012→2015 之间被重构 |

### 2.8 六比特层（kind 0x106 资源 #0）：不变性 + 统计法失效（第十六轮新增）

| 项 | 值 |
|---|---|
| 长度 / SHA-256 | 2,359,296 B / `93c4e55881cde2ae…`（已检查 **30 个固件全部一致，0 未命中**） |
| 覆盖机型 | E-P5 1.8、E-P7 家族(085/086/087)、E-M10 1.6、E-M10 III 1.4/1.5/1.6、E-P3 1.4、E-PM1 1.4、**E-M1 4.6**、**E-M10 II 1.3/1.4**、**E-P7 1.2** |
| 符号集 | 63 个（0x00–0x3B, 0x3D–0x3F），**`0x3C` 结构性缺席** |
| 熵 | 5.8326 bit/byte；符号频率全部量化到 **1/256 的整数倍** |
| 残余类 | k = 2…64 每个残余类都出现全部 63 个符号、分布几乎相同 ⇒ **无比特平面转置 / 无定长记录步长 / 无 4:3 重打包对齐** |
| 自相关 | shift1 = 0.0199（= Σp² 基线），各 shift 均 0.015–0.026 ⇒ **无任何周期** |
| 逐 bit 概率 | bit0 53.2% → bit5 38.3%，且在 k=4/k=8 残余类内完全一致 ⇒ 与位置无关 |
| 消费者 | 块 0 全量反汇编中**无任何指令以立即数引用** `0x43DA0400/0x43DA0020/0x43DA0000/0x427C0800` ⇒ 只能经运行时表间接取得，解码器疑在 **mask ROM** |
| **结论** | **平台级静态资源**；**不可能**承载任何版本差异（含 2018-12-18 松下镜头 AF 修复） |

### 2.9 新差分对：E-M10 II v1.3 → v1.4（第十六轮新增，构建时间正跨 AF 修复发布窗口）

| 项 | v1.3 | v1.4 |
|---|---|---|
| 构建时间（内层块时间戳） | 2018-04-11 00:49:04–08 UTC | 2018-12-13 02:59:41–53 UTC |
| 编译器日期串 | `Apr 11 2018` | `Dec 13 2018` |
| 块 1（数据 kind 0x101） | 27,262,912 B | **逐字节完全相同**（0 差异） |
| 块 2（资源 kind 0x106） | 20,971,456 B | **仅 48 B 差异**（12 × 4B，全部是构建时间戳字段） |
| 块 0（代码） | 21,364,672 B | 2,290,985 B 差异（10.723%，231,959 区间），表现为 **mask ROM 重链接位移 +0x1F** |

**同址锚点**（可作指令级差分的稳定窗口）：`0x26412B..0x2643A9`、`0x13D4A6..0x13D5CA`、
`0x166F78..0x1671C5`、`0xEA466B..0xEA47D7`、`0x13DEA4..0x13DF78`；
**位移锚点**：`disp=0x1C` 簇 `0x530B2E → 0x530B4D`（+0x1F）。

**镜头 ID 处理路径（已定位）**：E-P5 指纹序列 `90 0e f1 78 f0 40` 在 E-M10 II 两版块 0 中
各只命中 1 处（v1.3 @ `0x4083C6F2`，v1.4 @ `0x4083C711`，相差 +0x1F）。
该函数及其查表段**逐条指令完全相同**，差异仅 **代码 +0x1F / RAM +0x10**；
镜头主表（`0x4047A400`，90 条）**720 B 逐字节相同**；镜头字符串区（922 条）内差异仅 160 B。

> **⇒ E-M10 II v1.3 → v1.4 在镜头子系统的代码与数据上都没有语义变化。**
> ⚠️ **第十七轮更正**：本对的**修复版本是 v1.3（2018-05-10，第二波松下修复）**，
> v1.4（2019-03-07）的内容是"SD 卡 UHS-II 稳定性"与"LIVE TIME 稳定性"。
> ⇒ **v1.3→v1.4 本来就与 AF 修复无关**，本节的"无语义变化"结论虽成立但**不能用于推断 AF 修复去向**。
> 详见 `evidence/af_fix_2018/round17_panasonic_fix_matrix_and_localization.md` §1.3。

**差异的空间分布**：块 0 未变化 19,073,687 B（**89.3%**），差异集中在 `0x40500000–0x409FFFFF`（约 5 MB）；
含全部镜头字符串的低地址区几乎不动。


### 2.10 ★ 松下 AF 修复：官方矩阵 + 地面真值差分对 + 镜头 ID 链证伪（第十七轮新增）

**证据文件**：`evidence/af_fix_2018/round17_panasonic_fix_matrix_and_localization.md`
（机读摘要 `round17_summary.json`；官方发布说明存档 `firmware/notes/release_notes/`，16 页）

#### (a) 官方发布说明矩阵（观察）

松下 H-ES200 / H-ES50200 的 AF 修复共**三波**：

| 发布日 | 机型（版本） |
|---|---|
| 2018-02-28 | E-M5 II v4.0、E-M1 II v2.0（仅 H-ES200） |
| 2018-05-10 | E-P7 v1.4、E-M10 II v1.3、E-M10 III v1.1（H-ES200 + H-ES50200） |
| **2018-12-18** | **E-P3 v1.6、E-PL3 v1.6、E-PM1 v1.6、E-M5 v2.3、E-PL5 v1.6、E-PM2 v1.6、E-P5 v1.8、E-PL6 v1.4、E-M10 v1.4**（9 机联合发布） |

⇒ **目标本体 E-P5 v1.8 确属 2018-12-18 修复波**，项目日期前提成立。
⇒ 上一轮选的差分对（E-M10 II v1.3→v1.4）**选错了版本边界**，本轮已纠正。

#### (b) 地面真值差分对：修复前 / 修复后**本地已有**（观察）

`firmware/pre_fix/` 里已有 **两个相互独立机型族**的「修复前 → 修复后」样本：

| 差分对 | 块 0 差异 | 非代码分区（0x101 / 0x104 / 0x106 / 0x107） |
|---|---|---|
| E-PM2 v1.5.0.1 → v1.6.0.0 | 2,969,352 / 14,155,712 B（20.98%） | **全部逐字节完全相同** |
| E-M5 v2.2.0.2 → v2.3.0.0 | 3,319,143 / 14,155,712 B（23.45%） | **全部逐字节完全相同** |

⇒ **AF 修复不在数据分区、不在资源容器**，落点必在**代码块 0** 内。

#### (c) ★ 镜头 ID 比较链：修复前后**完全一致** ⇒ 证伪上一轮推断（观察）

`tools/lens_chain_scan.py` 全 disp 扫描结果：

| 固件 | 窗口 | 高字节 | 次字节 |
|---|---|---|---|
| E-PM2 **v1.5（修复前）** | `0x403D3D3E..0x403D3E3E` | `C1 C0 81` | `80 00 F1 E1 80 F1 E3 F1 28` |
| E-PM2 **v1.6（修复后）** | `0x403D3D3E..0x403D3E3E` | `C1 C0 81` | `80 00 F1 E1 80 F1 E3 F1 28` |
| E-P5 **v1.8（目标）** | `0x403B7975..0x403B7A75` | `C1 C0 81` | `39 80 00 F1 E1 80 F1 E3 F1 28 39` |

⇒ 修复**未新增/删除/修改任何镜头 ID 白名单项**。
⇒ **上一轮"候选补丁字节 = `0xC0F1` / `0xC0E1`"被证伪**（这两项修复前就存在）。
⇒ 修复不是"把松下镜头加进 ID 白名单"，而是**改变对既有镜头 ID 的处理行为**。

#### (d) ★ 唯一可复现签名：`fcs_lens_mfts_move_lens_ofset_target`（观察）

全固件标识符集合差分（E-PM2 6,806 / 6,805；E-M5 6,547 / 6,546）：

| 固件 | `fcs_lens_mfts_move_lens_ofset_target` 命中 |
|---|---|
| E-PM2 v1.5（修复前） | **1** |
| E-PM2 v1.6（修复后） | 0 |
| E-M5 v2.2（修复前） | **1** |
| E-M5 v2.3（修复后） | 0 |
| **E-PL6 v1.4（修复后，新取）** | **0** |
| **E-M10 v1.4（修复后，新取；不同平台代）** | **0** |
| **E-P5 v1.8（目标本体）** | **0** |

**四个独立机型族**（E-PM2 / E-M5 / E-PL6 / E-M10）给出同一条唯一签名 ⇒ 非噪声；
其中 E-M10 v1.4 属**完全不同的平台代**（3 块 / 块 0 基址 `0x40300020` / 18,874,304 B）
⇒ 该签名**跨平台代成立**，是平台级组件行为。
⇒ **AF 修复落点收窄到 `fcs_lens_mfts`（镜头 AF 驱动）模块**，形态是
`move_lens_ofset_target()`（「带 AF 目标偏移的镜头移动」）被**移除或合并**。

#### (e) 代码块差异的性质（观察）

E-PM2 v1.5→v1.6 块 0 差异 2,969,985 B 按指令字段分类：2 字节指令字段 48%、
`mov` 立即数 11%、`call` 相对偏移 10%、6 字节 `fc` 32 位立即数 8%、**真数据区仅 1%**。
区域级判定（8,769 个变化区）：205 区（413,391 B）可精确匹配到 B 的别处 ⇒ **整体搬移**，
主位移 `+16 / +684 / +648`。唯一"无对应内容"的大区 `0x4E3B12..0x4F1BB2`（57,504 B）
经反汇编查明是 `movbu d0,(0x605CD2xx)` 的 **RAM 地址 +0x10 位移**，写入值序列完全相同 ⇒ 布局位移。

#### (f) 标定对：一次真实功能新增长什么样（观察）

E-M5 III v1.4→v1.5（新增 8-25mm F4.0 PRO 焦点堆叠）：块 1 / 块 3 / 块 4 逐字节相同，
块 2 仅 96 B 差异（**全是构建时间戳**），块 0 差异 17.27%。
语义改动指纹 = **新增标识符串**（如 `seek_last_wait`）+ **新增数据表** + 代码块差异。
⇒ 松下修复**只表现为标识符串被移除，不引入任何新参数表**。

#### (g) OMSRV 官方接口现状（观察）

`POST https://fw01.om-digitalsolutions.net/ww_inform/fcache.do` **仍在线**，
返回带签名的固件直链（`?Expires=&Signature=&Key-Pair-Id=`，有效期约 3 分钟）——
**这解释了历史上"官方直链 403"的真正原因**：未签名路径被 CloudFront 拦（`MissingKey`）。
请求体关键点：**`<hard_code>` 必须是 16 字符** `OLYE` + 机型码**前 3 位** + 9 个 `0`
（写成 4 位机型码会得到退化响应）；`<time>`/`<mac_address>` 需沿用官方样本值。
但参数全扫描（`firmup_mode` / `type` / `hard_code` / `version` / 4 个端点）表明
**该接口只提供最新版**；签名与路径绑定（换文件名即 403）。
旧 `indexNN a.html` 页全部存在但**只有发布说明、无固件链接**；
Wayback 每机型**只存最新版**；xdel.ru 被 DNS sinkhole。
⇒ **历史版本固件公网已不可得**，必须靠 `pre_fix/` 已有样本做差分。

**OMSrv 的 `up_date` 字段构成第二个独立官方源**：9 个 2018-12-18 机型逐一查询，
`up_date` **全部 = `2018/12/18`**，与发布说明页完全一致（双源互证）。

**三重校验**：用 OMSRV 签名直链取回仓库里两个缺失的 2018-12-18 修复版本
（E-PL6 v1.4、E-M10 v1.4），其 SHA-256 与 MANIFEST、仓库 git blob **三者完全一致**
⇒ 官方服务器 / 仓库清单 / 仓库实体互证；且说明 `firmware/pre_fix/` 里那两个 0 字节文件
**只是本地工作区残留，仓库本体从未损坏**（sparse-checkout 下 `git checkout` 被拦，
需用 `git show HEAD:<path>` 取出）。


---

## 3. 已排除的假设（全部有可复现证据）

| # | 假设 | 排除依据 | 工具 |
|---|---|---|---|
| 1 | AF 修复在「镜头 ID 前缀比较链」 | E-M5 v2.2/v2.3 **与** E-PM2 v1.5/v1.6 双机型：链 7 项完全相同 | `lens_compare.py` |
| 2 | AF 修复在「LENS_INFO 镜头主表」 | 同上：106 条完全相同 | `lens_compare.py` |
| 3 | AF 修复在块 1 / 2 / 3 | 全块差分：这三块**逐字节相同** | `blockdiff.py` |
| 4 | AF 修复是"新增镜头型号名" | 版本间有意义标识符增减 = **0** | `str_delta.py` |
| 5 | AF 修复在第二张镜头 ID 表 | 全块扫描只有 LENS_INFO 一张 | `find_lens_tables.py` |
| 6 | AF 修复是"新增比较常量" | 0xC0/0xC1 频次未变；0x80 +1 属重构噪声量级 | `cmp_hist.py` |
| 7 | `art_*` 名字可用来定位滤镜代码 | Ghidra 全量验证：**0 引用**（6,488,149 条指令） | `Mn103FindArtRefs` |
| 19 | 「AF 修复是 `.BIN` 里的某段字节」 | **第十五轮**：镜头/AF 代码区修复前后逐条指令相同；mask ROM 映像既不在 `.BIN` 也不在更新包 ⇒ **`.BIN` 里不存在该修复的补丁字节** | 
| 8 | 块 0 存在「ID 索引指针表」 | 唯一命中是 `0x90909090` 填充假阳性 | `find_ptr_tables.py` |
| 9 | 块内字符串可用立即数寻址 | 62,167 条里**只有 1 条**被 `fc <imm32>` 引用 | `Mn103FindArtRefs` |
| 10 | `0x406F030C` 等 4 处是「mode 哈希表」（值 102–130） | 实为 **mask ROM 指针表**（`0x7E84xxxx`，步长 0x0C/0x08），不含小整数 ID | `dump_region.py` |
| 11 | `art_*` 函数名目录旁边有**同序的函数地址表** | 用 21 项互异、跨度 ≤0x40000 的函数指针数组全块搜索：**0 组** | `find_fn_ptr_arrays.py` |
| 12 | 第十三轮结论「A04F 是唯一空缺资源 ID」「4 个已实现滤镜名字已在块 1」 | `A04F` = "MF" 辅助文字；空闲 ID 是 `A049/A04B/A04C/A04E`；`Clear Line` 在 v1.8 块 1 **0 次** | `block1_art_id_map.py` |
| 13 | E-M10 的 Picture Mode 地址模板可直接套到 E-P5 | E-P5 是**资源 ID 段**（`A03F`–`A048`）+ 录像 4 项，组织方式不同 | `block1_art_id_dump.py` |
| 14 | AF 修复在「镜头 ID 前缀比较链」 | **指令级差分**：E-PM2 1.5 MB 窗口 645,858 条指令**零插入零删除**；链在两版**地址完全不动** | `instr_diff.py` |
| 15 | AF 修复在「镜头 ID 组装 / 选 ROM 参数」指令 | 该函数 4 KB 窗口修复前后**仅 2 字节**不同，且为 ROM 地址位移 | `instr_diff.py` |
| 16 | AF 修复在镜头子系统 6 张 mask ROM 指针表 | 按表位移归一化后**逐项相同**（E-PM2 + E-M5 双机型） | `lens_rom_tables.py` |
| 17 | AF 修复在镜头/AF 代码区 | 指令级差分：零插入零删除，差异全为 ROM 位移 + 链接噪声 | `instr_diff.py` |
| 18 | AF 修复在块 1/2/3/4 | 逐字节相同（E-PM2 三版、E-M5 两版交叉验证） | `decode_any.py` |

---

## 4. 差分管线的三重校准（方法论可靠性证据）

| 校准 | 内容 |
|---|---|
| 社区补丁 | E-M5 II v4.1 补丁偏移与 fishcu 独立记录 `0x3f2ad5/0x534866/0x53486c` **完全吻合** |
| 容器往返 | `decode → encode` 与源文件 SHA-256 **完全相同** |
| 版本常量 | 语义差分**自动找出** `0x2202→0x2300`（E-M5）与 `0x1501→0x1600`（E-PM2），相似度 0.993–0.998，各改 1 token |

---

## 5. 固件来源（重要）

| 来源 | 内容 | 备注 |
|---|---|---|
| **xdel.ru** `original/` + `pre_fix/` | 57 个原版固件，**含同机型历史版本** | **修复前基线的唯一来源** |
| xdel.ru `patched/` | 13 个社区改机归档 | 解锁功能的字节级先例 |
| Wayback `dl01.om-digitalsolutions.net/OMDS/FIRMWARES/0001/<model>/` | 52 个 `.BIN` | **只存最新一版**（5 域名 / 21,038 URL 全量普查确认） |
| 官方直链 | — | 403（CloudFront 签名失效） |

**对照固件清单**（本地，不入仓）：
E-M5 v2.0/v2.1/v2.2（修复前）+ v2.3；E-PM2 v1.1–v1.5（修复前）+ v1.6；
E-P3 v1.6、E-PL3 v1.6、E-PM1 v1.6、E-PL5 v1.6、E-PM2 v1.6、E-PL6 v1.4、E-M10 v1.4；
E-M10 II v1.3/v1.4、E-M1 II v3.0/3.4/3.5/3.6/3.7、E-M1 III v1.2/1.3/1.5/1.6、
E-M5 III v1.4/1.5/1.7、E-M1X v1.3/2.1/2.4、E-M1 v4.6、E-M5 II v4.1、PEN-F v3.1/3.1.1、
E-M10 III v1.2、E-M10 IV v1.1、E-PL7 v1.4、E-PL8 v1.1、E-PL9 v1.1、E-PL1 v1.3、E-PL1s v1.2

---

## 6. 证据目录导航

```
evidence/
  af_fix_2018/
    af_fix_v22_v23_negative_result.md   v2.2→v2.3 证伪「修复在镜头 ID 结构」
    af_fix_block_scope.md                双机型复现 + 全块差分（修复只在块 0）
    af_fix_localization.md               排除清单 + 下一步的确切做法
    af_fix_cross_model.json              6 机型镜头结构对照
    model_release_history.json           28 型号官方版本沿革
    lens_prefix_chain_E-P5_1.8.txt / _E-P3_1.6.txt   比较链反汇编快照
  fw_layout/                              ★ 第十六轮新增：容器/分区格式
    round16_container_layout_and_blk106.md  容器两层结构 / 每块构建时间戳 / 资源容器 / 六比特层不变性 / E-M10 II 新差分对 / 地址约定更正
    round16_summary.json                    机器可读摘要（含更正后坐标）
  art_filter/
    art_filter_analysis.md               子系统分析（效果 ID 空间 / pass / 门控 / 否定结论）
    art_filter_address_map.md            ★ 完整地址地图 + 新增滤镜/解锁模板
    art_filter_menu_and_ids.md           ★ ID 命名空间 / 菜单资源映射 / 录像只 4 项（第十四轮）
    art_effect_ids.json                  效果 ID 与函数名清单
    art_inventory_v18.json               13 模块 + 两套命名空间 + MODE_EXPOSE + COLORTONE
    res_desc_table_v18.json              块 0 UI 字符串资源描述符表（99 条）
    block1_art_id_map.json               块 1 资源 ID ↔ 艺术滤镜名（精确整串匹配）
    block1_filter_names.json             块 1 UI 名字与资源 ID（第十三轮；已知有偏移错位，勿单独引用）
    block1_res_id_map.json               块 1 全部字符串资源 ID
    lens_info_table.json                 LENS_INFO 镜头主表
  patched_community/
    community_patch_table.md             ★ 社区改机补丁字节表（3 个通用模式）
    patched_community.json               机器可读补丁表
```

文档：

```
docs/
  PROJECT_STATUS.md                      ★ 现状总表（本文件）
  RE_METHOD_PLAYBOOK.md                 方法论手册
  subsystem_map.md                      固件子系统全景测绘
  external_research.md                  ★ GitHub 奥林巴斯逆向项目调研笔记（外部资料转述）
```

---

## 7. 下一步队列

| 优先级 | 任务 | 状态 |
|---|---|---|
| P0 | 判定「录像菜单只 4 项」的成因：mask ROM 描述符里的列表短，还是块 0 侧 `flags` 门控 | 🔜 **决定"能否加菜单项"** |
| P0 | 逐个检查 13 个滤镜模块的初始化函数 → 产出「哪些滤镜在 E-P5 上被锁、锁在哪条指令」清单 | 🔜 |
| P0 | 按模板 A 实做一个新滤镜的 312 B 参数块，验证落盘方案 | 🔜 |
| P1 | 追 `mov_art.c` 16 字节记录表的 `id` 字段 → 建立 `MODE_EXPOSE` 22 项 ↔ `COLORTONE` 12 项 ↔ 模块 ID 的映射 | 🔜 |
| P1 | AF 修复：定位打印 `af_data_pos[%d]` 的函数 → 读出 `LENS_INFO` 各字段偏移与 `af_data_pos[]` 项数（须按**指令解码**反解基址，不能按 2 字节模式统计） | 🔜 |
| P1 | AF 修复：转而查「AF 控制流程的新分支」与「镜头 I²C 应答处理（`LENS_ASKDATA_MODE_*`，34 字段）」—— 参数在 ROM，这两条是仅存的路 | ⚠️ **第十五轮已把范围压到「镜头/AF 代码区」**：E-PM2 1.5 MB / E-M5 576 KB 窗口内指令级零改动 ⇒ **AF 控制流程若在 `.BIN` 里，必在镜头子系统之外** | 
| **P0** | **确认机身 mask ROM 映像（`0x7Exxxxxx`）的交付方式** | ✅ **第十五轮已答**：四项独立检验（容器算术 / 块运行时地址 / 块 0 位移扫描 / 更新包与服务器）一致表明 **ROM 映像既不在 `.BIN` 里，也不随固件更新下发** ⇒ 修复实体不在可刷的固件包内 |
| P1 | 块 1 主文本池零填充段清单 → 确认是否有"不需等长替换"的新增名字途径 | 🔜 |
| P2 | 解 6 个 RAR 改机归档，补全社区补丁表（需 `unrar` / 7-Zip，本机均缺失） | 🔜 |
| P2 | 块 2 的 6-bit 编码 | ⛔ **第十六轮定性**：跨 **30 个已检查固件（0 未命中）/ 8 机型族 / 2012–2022** **逐字节恒定** ⇒ 不是任何版本差异的载体；统计法（差分/频率/对齐）已证明失效，**解码器疑在 mask ROM**，降为背景项（见 `evidence/fw_layout/round16_container_layout_and_blk106.md`） |
| **P0** | ~~**E-M10 II v1.3 → v1.4 差分对**：判断 v1.4 是否含松下镜头 AF 修复~~ | ✅ **第十七轮已澄清**：v1.3（2018-05-10）才是第二波修复版，v1.4 是"SD 卡 / LIVE TIME 稳定性"⇒ **本对选错了版本边界，已作废**；正确的地面真值对见 §2.10(b) |
| **P0** | **解开断言串的引用机制**（`fcs_lens_mfts_move_lens_ofset_target` 在固件内**无 u32 指针引用**）→ 定位该函数入口与调用点 | 🔜 **第十七轮新增的关键阻塞点**；解开它才能取到函数体 |
| **P0** | **在 E-PM2 v1.5 vs v1.6 上比对 `move_lens_ofset_target` 函数体** ⇒ 得到补丁的指令级形态 | 🔜 地面真值对已就位，只差函数定位 |
| **P0** | **用同样的指令级形态在 E-P5 v1.8 内定位** ⇒ 给出补丁字节坐标 | 🔜 |
| **P1** | **用 E-M5 v2.2 vs v2.3 独立复核**（同形态、同结论 ⇒ 交叉验证成立） | 🔜 |
| **P1** | **地址约定 +0x20 更正**：把历史 E-P5 坐标与新规范换算对齐 | 🔜 结论已成立（容器工具定义 + 块 2 自述地址自证），**本轮只标注未批量改写历史文件**；需一次性复核 `evidence/`、`report/`、`docs/` 中的绝对地址 |
| **P1** | **构建时间戳当作跨版本对齐锚点** | 🔜 内层块头 `[24:28]` 提供天然时间锚；可用于把"哪几块在同一批次构建"判出来，替代脆弱的"按地址对齐" |
| P1 | 资源目录 40 条的业务含义（尤其是否含 Art Filter / 色彩 LUT） | 🔜 已知含 JPEG（示例照片）与数据表；LUT 待定位 |
| P3 | 实机刷写验证 / 实机 mask ROM dump | 需硬件 |

---

## 8. 版权与再分发边界

### 8.1 固件本体（自本轮起纳入仓库）

- **`firmware/` 目录收录了全部原始固件与社区改机归档**
  （66 个原版 + 17 个修复前基线 + 12 个社区归档 + 59 份采集资料，
  共 121 个文件 / 1,250 MB，**Git LFS** 存储）。
- 固件著作权**属于 Olympus（横滨奥林巴斯 / Taiyo Yuden）**，本项目不主张任何权利；
  这些文件取自 **xdel.ru**（泰语镜像站）与 Wayback。
- 文件仅供本项目的**逆向研究、备份与互操作分析**使用；
  **不得**用于商业目的、**不得**再分发、**不得**用于生成可分发的改机固件。
- 压缩件 `*.BIN.lzma` 为 **LZMA 无损**压缩：
  `firmware/MANIFEST.sha256` 的 ORIG 段记录了每个原始 `.BIN` 的 SHA-256，
  `tools/verify_firmware_bundle.py --deep` 会逐个解压还原并比对（当前 **50/50 全部一致**）。
- 详见 [`firmware/README.md`](../firmware/README.md)。

### 8.2 其余内容

- 分析产物（`evidence/`、`docs/`、`tools/`、`decoded/`、`disasm/`）为本项目原创，
  只含**坐标 / 长度 / SHA-256 / 指令文本 / 伪代码**，不含原厂二进制。
- `scripts/OlympusFw*.hxx`、`scripts/EstimateLoadAddress.hxx` 来自 `cmdada/em10-fw` 内的 vendor
  Olympus 官方工具 `oly_fw_tools`（仅用于说明格式定义）。
- `tools/oly_container.py` 来自 `fishcu/oly_fw_analysis`（其实现注明源自 Altsoph / mx3，
  CHDK thread 2471）。
- 本项目原创：其余 `tools/*.py`、`tools/ghidra/*.java`、`docs/`、`evidence/` 全部产物。
- 第三方引用见 [`PROVENANCE.md`](../PROVENANCE.md)。
