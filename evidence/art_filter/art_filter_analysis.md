# E-P5 1.8 艺术（创意）滤镜子系统 —— 逆向分析

> 日期：2026-10-22
> 目标固件：`OLY_E_108_1800_0000_0000.BIN`（E-P5 v1.8），块 0 基址 `0x402C0000`
> 方法：静态分析（字符串索引 + Ghidra 12.1.4 + MN10300 SLEIGH 模块）。**不含执行证据。**

---

## 0. 结论摘要

| 项 | 结论 |
|---|---|
| 创意滤镜是否在固件内实现 | **是**。块 0 内存在完整 `art_*` 子系统：5 个效果 ID、多 pass 管线、能力门控函数 |
| 效果 ID 空间 | **10 / 20 / 30 / 40 / 50** → `star_light` / `pinhole` / `frame` / `soft_focus` / `white_edge` |
| 滤镜 UI 名字在哪 | **块 1**（UTF-16LE 多语言字符串池 + `@A0xx@` 资源 ID 前缀） |
| 名字与 ID 的对应表 | **尚未定位**（见 §5 未解项） |
| `art_*` 名字能否直接定位代码 | **不能**。Ghidra 全量验证：6,488,149 条指令中 **0 条**引用这些字符串；数据段也无指针表 |
| 增益/参数表位置 | **尚未定位**（块 0 / 块 2 六位加密区 / mask ROM 三选一未定） |

---

## 1. 块 0 的 `art_*` 子系统（符号名池）

在 `decoded/strings.jsonl` 的 block 0 中提取到 **752 条** `art_*` 字符串，其中 251 条是纯函数名。
完整清单见 `art_effect_ids.json`。

### 1.1 效果 ID 空间

```
art_effect_10_star_light
art_effect_20_pinhole
art_effect_30_frame
art_effect_40_soft_focus
art_effect_50_white_edge
```

ID 均为 10 的倍数 ⇒ 编号空间按 10 预留，**存在可扩展的空位**（60/70/…）。

### 1.2 每个效果的 pass 管线

| 效果 | pass 数 | 附属函数 |
|---|---|---|
| `star_light` | **pass1..pass15**（15 段） | `art_star_light_get_inf` |
| `pinhole` | pass1..pass5 | `art_pinhole_set_gainmap` |
| `frame` | pass1..pass5 | `art_frame_get_jpeg_revision` / `art_frame_make` / `art_frame_check_param` / `art_frame_get_res_ID` / `art_frame_analyze_jpeg_header` / `art_frame_decord_jpeg` / `art_frame_disp_jpeg_revision` / `art_frame_free` |
| `soft_focus` | 多段 | — |
| `white_edge` | 多段 | — |

> 多 pass + `set_gainmap` ⇒ 效果由「若干处理阶段 + 增益图（曲线/LUT）」构成，
> 与奥林巴斯「艺术滤镜」在机内的实现形态一致。

### 1.3 控制 / 门控函数（**解锁功能的关键**）

```
art_init                 art_GetFilterType
art_IsSupportType        art_SendRequest
art_chk_type             art_chk_type_rec      art_chk_type_mov
art_chk_submode          art_chk_proccont      art_chk_effect
art_chk_effect_monotorn
```

- `art_chk_type_rec`（拍照）与 `art_chk_type_mov`（录像）**成对**出现
  ⇒ 存在「某滤镜是否允许用于录像」这一类独立判定，**这正是奥林巴斯后来用官方固件解锁的
  「电影艺术滤镜」那一类开关**。
- `art_IsSupportType` / `art_chk_effect` 是能力与效果白名单校验。
- `art_chk_effect_monotorn` 与「单色/色调类」效果（`Toned Color` / `Dramatic Tone` 一族）相关。

### 1.4 其他相关字符串

- `MODE_EXPOSE_DRAMATIC_TONE(_2[_MOVIE])`、`MODE_EXPOSE_WATERCOLOR(_MOVIE)`、
  `MODE_EXPOSE_GENTLE_SEPIA(_MOVIE)`、`MODE_EXPOSE_ROUGH_MONOCHROME(_MOVIE)`
  ⇒ 曝光模式族，**与 MOVIE 后缀成对**，再次印证「拍照/录像」两套判定。
- `IMG_FUNC_SEPIA`、`usRawSaturation` / `chSaturation` / `shSaturation`
  ⇒ 存在 `IMG_FUNC_*` 图像功能枚举表（曝光/色彩处理功能）。

---

## 2. `art_*` 字符串为何定位不到代码（Ghidra 全量验证）

这是本轮一个**重要的否定性结论**，纠正了"日志字符串可直接寻址"的直觉。

### 2.1 验证方法

安装 MN10300 的 Ghidra SLEIGH 模块后（见 `tools/ghidra/README.md`）：

1. **逐指令扫描**（`Mn103FindArtRefs.java`）：遍历块 0 全部
   **6,488,149** 条已解码指令，检查任一操作数标量是否落在 art 字符串所在页
   `0x40714000..0x40718000`。
   → **命中 0 条**。
2. **引用管理器查询**（`Mn103ArtStringRefs.java`）：对若干 art 字符串地址
   （如 `0x407155B0` `art_effect_20_pinhole`）查询 Ghidra 已知引用（代码 + 数据）。
   → **引用数 0**，且目标处未被定义为独立字符串对象（`defined data: <none>`）。
3. **裸 4 字节地址扫描**（Python）：在块 0 中搜索这些字符串的 32 位地址，
   752 条中仅 2 条偶然出现（间距 6 MB，明显是巧合）。

### 2.2 结论

`art_*` 是一份**残留的符号名表**（build 时带 trace/符号设施、但消费机制未链接进产物），
它**记录了子系统的词汇表，却不能用来定位实现代码**。

> ⚠️ 推论：块 0 内 62,167 条字符串里，**只有 1 条**（`CA_MAIN`）被 `fc <imm32>` 直接寻址。
> 奥林巴斯固件的块内字符串**普遍不是用立即数地址寻址的**，此前的"搜 `fc`"思路对整块固件无效。

### 2.3 由数值 ID 反推分派点（Ghidra）

`Mn103FindEffectSwitch.java` 在 56,980 个函数中扫描「同时比较 10/20/30/40/50」的函数：

```
命中 18 个函数；含 4 个不同效果 ID 的有 3 个：
  FUN_4047975c  ids=[20,30,40,50]
  FUN_4048b6d2  ids=[10,20,30,40]
  FUN_4049893c  ids=[10,20,30,40]
```

`FUN_4049893c` 反汇编（已与 objdump 基准逐指令核对）：

```asm
  0x40498940  MOVBU (0x1b ,A1),D0     ; D0 = 记录[+0x1B] = 模式/效果 ID
  0x40498943  CMP 0xa,D0              ; == 10
  0x40498945  BEQ 0x4049894b
  0x40498947  CMP 0x14,D0             ; == 20
  0x40498949  BNE 0x40498966
  0x4049894b  MOV (0x34 ,A1),D0       ; 取记录[+0x34]
  0x40498950  CMP 0x1,D0
  ...
  0x404989a8  MOV 0x78,D0             ; 默认返回 0x78 (120)
```

`FUN_4048b6d2` 则是 **16 字节步长的 u16 表驱动**函数
（`ASL 0x4,D0` = ×16，`MOVHU (D0,A1)` 取表项），与本项目早前用字节模式发现的
"cmp 10/20/30/40 每 16 字节等距" 位置完全吻合（`0x40498943`）。

> 这三个函数是**模式 ID 分派器**（含 `+0x1B` 字段、`+0x34` 子模式），
> 目前尚未证明它们就是 art 效果分派表 —— 仍需与 `art_chk_effect` 的语义对齐。

---

## 3. 块 1：UI 名字与资源 ID

块 1 = **UTF-16LE 多语言字符串池**（每条以 UTF-16 NUL 结束），22,937,536 B。
名字位置见 `block1_filter_names.json`。

### 3.1 E-P5 照片模式菜单定义（英文，块 1 偏移 `0x3543AC..0x3544EE`）

| 资源 ID | 名字 | 偏移 |
|---|---|---|
| A021 | i-Enhance | 0x3543AE |
| A07A | Vivid | 0x3543CE |
| A07C | Portrait | 0x3543E6 |
| A03F | **Pop Art** | 0x354404 |
| A040 | **Dramatic Tone** | 0x354178 |
| A041 | **Soft Focus** | 0x354420 |
| A042 | Pale&Light Color | 0x354442 |
| A043 | Light Tone | 0x354470 |
| A044 | **Grainy Film** | 0x354492 |
| A045 | **Pin Hole** | 0x3544B6 |
| A046 | Diorama | 0x3544D4 |
| A048 | Gentle Sepia | 0x354B60 |

资源 ID 是**连续编号**（A03F…A048），`@A0xx@` 前缀即资源 ID 占位符。

### 3.2 5 个 `art_*` 效果在块 1 中的对应

| 效果 ID | art 名 | UI 名 | 证据 |
|---|---|---|---|
| 20 | pinhole | **Pin Hole** | `A045@Pin Hole`（多处语言分区） |
| 40 | soft_focus | **Soft Focus** | `A041@Soft Focus`；另有 `dd Soft Focus Effect` |
| 10 | star_light | **Star Light** | `dd Star Light Effect`（意大利/德/丹等分区） |
| 50 | white_edge | **White Edge** | `dd White Edge Effect` |
| 30 | frame | （Frame） | 块 1 有 `Frame`（27 处，含非滤镜义，需消歧） |

> `dd … Effect` / `A0xx@` 两种前缀并存 ⇒ 至少两套菜单定义表（拍照 / 录像）。
> 这与 `art_chk_type_rec` / `art_chk_type_mov` 成对存在相互印证。

### 3.3 纯名字池（英文，偏移 `0x34EC2A..0x34ED12`）

按字母排序的一组：`Cross Process / Diorama / Dramatic Tone / Gentle Sepia /
Grainy Film / Light Tone / Pale&Light Color / Pop Art / Soft Focus / Pin Hole`。

---

## 4. 对「新增创意滤镜 / 解锁功能」的可行性评估

### 4.1 新增滤镜：需要动的地方（按依赖顺序）

1. **块 0**：效果注册表（ID → 处理函数/参数块）—— **待定位**。
   新增 ID（如 60）需在此登记。
2. **块 0**：效果实现（pass 函数 + 增益图）。
   **最低风险路径：克隆一个既有效果的 pass 链，只换参数/增益图**，得到"新观感"。
3. **块 1**：新滤镜的 UI 名字（多语言 UTF-16LE）＋ 菜单定义表项。
4. **块 0**：`art_chk_effect` 白名单 + `art_IsSupportType` 能力判定（若新滤镜默认关闭）。
5. **块 0**：`art_chk_type_rec` / `art_chk_type_mov` —— **这就是"解锁录像滤镜"的开关**。
6. 容器重打包 + sum32 重算（**已具备**：`tools/oly_container.py` 的 `replace_payload()`）。

### 4.2 解锁功能：已定位的门控点

| 门控 | 位置 | 说明 |
|---|---|---|
| 艺术滤镜录像开关 | `art_chk_type_mov` | 与 `art_chk_type_rec` 成对 |
| 效果白名单 | `art_chk_effect` | 校验效果 ID |
| 能力判定 | `art_IsSupportType` | 滤镜类型是否被支持 |
| 通用 feature 位 | 如 `0x605339A0`（bit0..4 已知语义） | 固件内多处 feature 掩码 |
| 机身型号码 | 容器头 `model_bytes` = `"1080"` | 奥林巴斯经典的"伪装型号解锁"路径 |

---

## 5. 未解项 / 下一步

| # | 未解项 | 下一步手段 |
|---|---|---|
| 1 | 效果注册表（ID → 函数/参数） | 在 Ghidra 中对 `FUN_4048b6d2` 等 3 个候选做深度分析；或从 `art_pinhole_set_gainmap` 的增益图数据反查 |
| 2 | 增益图 / 参数表位置 | 三选一：块 0 纯数据 / 块 2 六位加密区 / 机身 mask ROM。**块 2 的 6-bit 编码仍未解** |
| 3 | `art_*` 符号名 ↔ 实际函数地址的对应 | 名字表无引用，只能靠**行为/数值**反推（如某函数引用了 `pinhole` 的增益表） |
| 4 | `IMG_FUNC_*` 图像功能枚举表 | 块 0 内找 `{IMG_FUNC_*, u32}` 结构；`MODE_EXPOSE_*` 与 art 效果的对应关系 |
| 5 | 录像滤镜解锁的准确字节 | 需先完成 #1（找到 `art_chk_type_mov` 的实际地址） |

---

## 6. 复现

```sh
# 提取 art 效果 ID 与函数名
python tools/gen_art_evidence.py

# 提取比较链 + LENS_INFO 表
python tools/ep5_lens.py chain decoded/00_0100_402c0020.decoded.bin 0x402C0000
python tools/ep5_lens.py table decoded/00_0100_402c0020.decoded.bin 0x402C0000

# Ghidra 全量扫描（需先按 tools/ghidra/README.md 安装 MN10300 模块）
#   Mn103FindArtRefs.java     -> art 字符串引用（结果：0 命中）
#   Mn103FindEffectSwitch.java-> 效果 ID 分派函数（3 个候选）
#   Mn103DumpFuncs.java       -> 指定函数完整反汇编
```

> Ghidra 侧脚本需要已导入并完成批量反汇编的 Ghidra 工程；
> 工程与安装脚本见 `tools/ghidra/README.md`。
