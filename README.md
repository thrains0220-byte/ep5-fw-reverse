# ep5-fw-reverse — 奥林巴斯 PEN E-P5 固件 (Ver. 1.8) 逆向分析

对官方 E-P5 机身固件 `OLY_E_108_1800_0000_0000.BIN` 的离线静态逆向成果。

**容器格式已 100% 破解并逐字节验证**；指令集确认为 **Panasonic MN1030/MN103S**；已建立可用的 MN103 反汇编管线，
并还原出机身内存映射、镜头信息结构体布局与固件升级状态机。

> **固件本体说明**：本仓库的 `firmware/` 目录**收录了分析所需的原始固件与社区改机归档**
> （66 个原版 + 17 个修复前基线 + 12 个社区归档 + 59 份采集资料，1,250 MB）。
> 固件著作权属 **Olympus / OM SYSTEM（横滨奥林巴斯 / Taiyo Yuden）**，本项目**不主张任何权利**；
> 收录目的为**离线逆向研究、备份与互操作分析**。
> 逐文件 SHA-256 与还原校验见 [`firmware/README.md`](firmware/README.md) 与 [`firmware/MANIFEST.sha256`](firmware/MANIFEST.sha256)。
> **本项目原创部分**（代码 / 文档 / 证据）适用 [`LICENSE`](LICENSE)。

---

## 快速结论

| 项 | 结论 |
|---|---|
| 目标 | `OLY_E_108_1800_0000_0000.BIN`，44,826,624 B，SHA-256 `cc59a4e1…b5cfd` |
| 容器 | Olympus「OE」混淆块容器，4 块 × (32B 头 + payload + 32B 尾) |
| 混淆 | 16 字节内 16 列字节置换 + 全字节 XOR 0xFF |
| 校验 | **加法 sum32**（`-Σ(u32 LE)`），非 CRC32 |
| 指令集 | MN1030/MN103S，16 位 RISC，小端 |
| 往返验证 | `decode → encode` 与源文件 SHA-256 完全相同；4/4 块校验和吻合 |

### 四个块

| # | flags | 官方含义 | payload | 装载地址 |
|---|---|---|---|---|
| 0 | `0x0100` | 主控 MCU 代码 | 15,728,576 | `0x402C0000` |
| 1 | `0x0101` | 多语言字符串 + 字体 | 22,937,536 | `0x427C0000` |
| 2 | `0x0106` | 内容域 [0x00;0x3F] | 2,490,304 | `0x43DA0000` |
| 3 | `0x0104` | 图片（照片文字叠加） | 3,669,952 | `0x44000000` |

### 最有价值的三个发现

1. **尾部"CRC32"其实不是 CRC**——是加法 sum32。这一点让常规 CRC 穷举全部落空。
2. **块 2 的 6-bit 区与 E-PL3(2011) 逐字节相同**（SHA-256 `93c4e558…`）→ 是跨代共享资产，
   **1.8 的 AF 修复不可能在其中**，据此排除了一整条错误方向。
3. **PC 端更新器完全不解析 OE 容器**（全部 updater 二进制搜魔数 `OE\x10\x80` 零命中）
   → 容器由机身 bootloader 解析，混淆还原也在机身侧完成。

---

## 目录导航

```
report/    完整逆向分析报告（v2，含全部字段表、结构体偏移、引用来源）
decoded/   混淆还原后的 4 个块 + 容器元数据 + 全部字符串索引
disasm/    MN103 反汇编样本（入口代码 / 内存映射表 / 镜头信息函数 / 镜头状态机）
firmware/  ★ 原始固件与社区改机归档（1,250 MB；含 SHA-256 清单与还原说明）
evidence/  REA 6.4.0 原始 Evidence JSON（Binwalk 扫描 / Unblob 提取 / PE 资源）
           + af_fix_2018/：AF 修复专题
               ├ af_fix_v22_v23_negative_result.md —— v2.2→v2.3 证伪「修复在镜头 ID 结构」
               ├ af_fix_block_scope.md              —— 双机型复现 + 全块差分（修复只在块 0）
               ├ af_fix_localization.md            —— 排除清单 + 下一步的确切做法
               └ lens_info_af_layout.md            —— LENS_INFO 结构自描述字段图 + mask ROM 边界
           + art_filter/：艺术（创意）滤镜子系统专题
               ├ art_filter_menu_and_ids.md        —— ★ 两套 ID 命名空间 / 13 个模块 / 菜单资源映射
               ├ menu_descriptor_typecode.md       —— ★ 类型码 → mask ROM 描述符机制 + 1 字节补丁配方
               └ art_filter_address_map.md         —— 完整地址地图 + 新增滤镜/解锁模板
           + patched_community/：社区改机归档的字节级补丁表（解锁功能模板）
               ├ community_patch_table.md          —— ★ 12/12 归档全量补丁表
               └ unlock_semantics.md               —— ★ 社区解锁补丁的语义解码
scripts/   可复现分析脚本 + Olympus 官方 oly_fw_tools 源码（格式权威定义）
tools/     第三方参考实现（fishcu/oly_fw_analysis 的容器解析器）+ 工具链构建脚本
           + ep5_lens.py / lens_compare.py / fw_diff.py（镜头结构提取与跨版本差分）
           + ghidra/（MN10300 Ghidra 模块部署 + 本项目 GhidraScript）
docs/      PROJECT_STATUS.md（现状总表）/ RE_METHOD_PLAYBOOK.md（方法论）/ subsystem_map.md
           / external_research.md（GitHub 奥林巴斯逆向项目调研）
reproduce.sh              一键复现：校验 → 解混淆 → 反汇编
PROVENANCE.md             逐项来源、许可与再分发边界
工作日志.md                逐日工作日志（结论、证据、阻塞与下一步）
固件本体说明.md            固件获取与校验说明
```

---

## 2026-10-22 新增：艺术滤镜子系统 / 解锁 / AF 修复定位

### A. 艺术（创意）滤镜：**确认在固件内实现**

块 0 内存在完整 `art_*` 子系统（`evidence/art_filter/art_filter_analysis.md`）：

| 效果 ID | 名称 | pass 管线 |
|---|---|---|
| 10 | `star_light`（星光） | pass1..pass15 + `get_inf` |
| 20 | `pinhole`（针孔） | pass1..pass5 + `set_gainmap` |
| 30 | `frame`（画框） | pass1..pass5 + JPEG 边框处理 |
| 40 | `soft_focus`（柔焦） | 多 pass |
| 50 | `white_edge`（白边） | 多 pass |

门控函数：`art_init` / `art_IsSupportType` / `art_GetFilterType` /
`art_chk_effect` / `art_chk_type_rec`（拍照） / `art_chk_type_mov`（**录像**）。

> `art_chk_type_rec` 与 `art_chk_type_mov` 成对存在 ⇒
> **「某滤镜是否允许用于录像」是一处独立开关**，即奥林巴斯后来用官方固件
> 解锁「电影艺术滤镜」那一类判定。

滤镜 UI 名字在块 1**（UTF-16LE 多语言字符串池），E-P5 照片模式菜单定义带连续资源 ID：
`A03F` Pop Art、`A040` Dramatic Tone、`A041` Soft Focus、`A042` Pale&Light Color、
`A043` Light Tone、`A044` Grainy Film、`A045` Pin Hole、`A046` Diorama、
`A047` Cross Process、`A048` Gentle Sepia。

#### A2. 艺术滤镜子系统完整地址地图（2026-10-22 第七轮，伪代码证据）

见 [`evidence/art_filter/art_filter_address_map.md`](evidence/art_filter/art_filter_address_map.md)。

| 语义 | 地址 |
|---|---|
| 效果 ID 全局 | `0x605FCD3C`（全部 9 处引用集中在 `0x4078844C–0x40789522`） |
| 效果类型全局（拍照/录像） | `0x605FCD40`（值 2 = 拍照） |
| **支持的类型位掩码** | `0x602AEB94` |
| 效果回调指针 | `0x602AEB54` |
| 效果参数区（当前生效） | `0x605FCD44`（312 字节） |
| 效果 50 参数模板 | `0x605FCE7C`（312 字节，恰好相隔 0x138） |
| 拍照参数区 / ROM 源 | `0x605FCA00` / `0x7E5C9809` |
| 录像参数区 / ROM 源 | `0x605FCCC4` / `0x7E5C9B1C` |
| 效果 ID 设置器 / 复位器 | `FUN_407887E0` / `FUN_40789519` |
| 子系统总初始化 | `FUN_407883DD` |
| 按类型初始化 | `FUN_40788616` / `FUN_4078866A` |

**⇒ 两个可直接落地的「新增滤镜」模板：**

- **模板 A（参数覆盖式，最低成本）**：新滤镜 = 312 字节参数块 + **复用既有效果的 pass 管线**。
  实证：`FUN_4078849B` / `FUN_40788562` 中把 `0x605FCE7C` 的 312 字节拷到 `0x605FCD44`，
  再 `FUN_407887E0(10)` 切回效果 10 的管线（效果 50 = 效果 10 + 参数覆盖）。
  **不需要写任何新的 DSP 代码。**
- **模板 B（独立效果）**：新 ID（下一个可用值 60）+ 独立参数块 + 独立 pass + 在初始化序列登记。

**⇒ 「解锁录像艺术滤镜」的三个具体落点：**

1. `0x602AEB94` 类型支持位掩码；
2. `FUN_40788616` 中 `param_1 == 2` 的拍照/录像分支判定；
3. 各效果初始化函数的类型白名单 —— `FUN_4078846D`（star_light）**同时**调用
   `FUN_4078866A(2)` 与 `FUN_4078866A(1)`，说明「只初始化拍照而不初始化录像」
   **正是艺术滤镜被锁的形态**。

> 录像滤镜的参数**本来就存在于机身 mask ROM**（`0x7E5C9B1C`），
> 固件侧只需搬运/使能 ⇒ 属于**可在固件内完成**的解锁。


### B. 工具链：Ghidra 现可原生反汇编 MN1030

`tools/ghidra/README.md` —— 第三方 SLEIGH 模块（`txt231/GhidraMn10300`）
+ Olympus 调用约定（`cmdada/em10-fw`），**与 objdump 基准逐指令一致（77/77，0 差异）**，
识别 **56,984** 个函数（艺术滤镜区 1,423 个）。

### C. 2018-12-18 松下 AF 修复：**已证伪"落在镜头 ID 结构"**

首次拿到**同机型"修复前/后"两版**（xdel.ru 的 E-M5 v2.2 / v2.3）：

| 结构 | v2.2（修复前） | v2.3（含修复） |
|---|---|---|
| 镜头 ID 前缀比较链 | 7 项 | **7 项，完全相同** |
| LENS_INFO 镜头主表 | 106 条 / 105 个唯一 ID | **完全相同** |

⇒ **修复不在镜头 ID 白名单、也不在镜头主表**，而在 AF 控制流程 /
每镜头 AF 参数组 / 镜头 I²C 应答处理。
详见 `evidence/af_fix_2018/af_fix_v22_v23_negative_result.md`。

### D. 社区"改机"归档：解锁功能的字节级先例

`evidence/patched_community/patched_community.json` —— xdel.ru 上 13 个社区
patched 归档，与原版固件逐字节差分后得到的**精确补丁表**。
两个反复出现的通用模式：

```
模式 A（12 字节，"解除某项限制"）:
  stock   1c a0 06 c8 14 a0 03 c8 10 a0 08 c8
  patched fc cc 10 00 00 70 60 88 1c df 80 1c

模式 B（2 字节，跳过一处判定）:
  stock   c8 07   ->   cb cb

模式 C（2 字节 ×2，改写跳转）:
  stock   cc 06   ->   90 7e
  stock   20 1c   ->   90 7e
```

出现于 E-M1 II v3.4/v3.6、E-M1 III v1.2、E-M5 III v1.4、E-M5 II v4.1、PEN-F v3.1。
⇒ **这些就是奥林巴斯"解锁功能"在固件里的真实字节级形态**，
是新增滤镜 / 解锁功能最直接的可复用模板。

### E. 本轮新增的否定性结论（重要）

- **`art_*` 字符串无法用于定位代码**：Ghidra 全量扫描 6,488,149 条指令，
  对 art 字符串区（`0x40714000..0x40718000`）**命中 0 条**；
  查询引用管理器，引用数同样为 **0**；裸地址扫描 752 条中仅 2 条偶然命中。
  ⇒ 它们是**残留的符号名表**，记录了子系统词汇表，却不指向实现。
  推论：块 0 的 62,167 条字符串里**只有 1 条**被立即数寻址，
  奥林巴斯固件的块内字符串普遍不能用"搜 `fc <imm32>`"的方式定位。
- **AF 修复不在镜头 ID 结构**（见 C）。
- **Wayback 无"修复前"基线**：5 个域名 / 21,038 URL 全量普查确认，
  2012–2013 代机型每个只存档了最新一版；更新器目录 `/ww/ud2/` 只有说明页。
  ⇒ 修复前基线只能来自 xdel.ru 这类镜像（E-M5 v2.0/v2.1/v2.2 即由此获得）。
- **公开世界不存在"机身侧 4 字节镜头 ID ↔ 镜头型号"对照表**
  （GitHub 仓库/代码搜索、grep.app、Sourcegraph、DuckDuckGo、archive.org 全查）。

---

## 已知未解问题

| 项 | 状态 |
|---|---|
| **1.8 AF 修复的补丁字节** | **原假设已证伪**：修复**不在**镜头 ID 前缀比较链、**不在** LENS_INFO 镜头主表（E-M5 v2.2 vs v2.3 结构完全相同）。剩余候选：AF 控制流程、每镜头 AF 参数组、镜头 I²C 应答处理。**修复前基线已获得**（E-M5 v2.0/v2.1/v2.2，来自 xdel.ru）。 |
| **艺术滤镜效果注册表**（效果 ID → 处理函数/参数块） | 未解。Ghidra 侧已锁定 3 个候选分派函数（`FUN_4047975c` / `FUN_4048b6d2` / `FUN_4049893c`），但尚未证明哪个是 art 效果表。`art_*` 名字表无引用，无法直接定位。 |
| **滤镜增益表 / 参数表位置** | 未解。块 0 / 块 2 六位加密区 / 机身 mask ROM 三选一未定。 |
| **录像艺术滤镜解锁的确切字节** | 未解。门控函数 `art_chk_type_mov` 的地址尚未确定。 |
| **块 1 多语言资源的菜单定义表** | 部分解。已定位 UTF-16LE 字符串池与 `@A0xx@` 资源 ID（照片模式 A03F–A048），但**"资源 ID → 效果 ID"的对应表未找到**。 |
| **H-ES200 / H-ES50200 的 4 字节镜头 ID** | 未解。固件内无镜头型号名字符串；ID 由镜头经 I²C 应答。公开世界亦无对照表。 |
| **块 2 的 6-bit 编码算法** | 未解。该 blob 与 E-PL3(2011) 逐字节相同，属跨代共享资产。 |
| ROM 描述符表 `0x7E5558E8` | 位于机身 mask ROM，不在固件镜像内。 |
| E-P5 SoC 全貌 | 本文件只含 1 个 MN103 核的代码；`IMG_CPU0_*` 暗示多核，其余核不在本镜像。 |

### `evidence/af_fix_2018/`（1.8 松下镜头 AF 修复专题）

| 文件 | 说明 |
|---|---|
| `model_release_history.json` | 从 Wayback 取回的**官方发布说明页**重建的 28 个型号完整版本沿革（含日期、是否含 H-ES200 条目） |
| `af_fix_cross_model.json` | 6 个固件（E-P5 1.8 / E-P3 1.6 / E-M10 1.4 / E-M10 III 1.2 / E-M5 III 1.1 / E-M1X 2.1）的镜头 ID 前缀比较链 + 厂商码比较表，含块 0 SHA-256 |
| `lens_prefix_chain_E-P5_1.8.txt` | E-P5 1.8 前缀链（`0x403B7965`）反汇编快照 |
| `lens_prefix_chain_E-P3_1.6.txt` | E-P3 v1.6 同一函数（`0x403EFBC5`）反汇编快照，用于逐指令对照 |

对照固件本体**不在本仓库**（版权），用 `scripts/get_one.sh` / `scripts/get_par.sh` 从
Wayback 重新取回后，用 `tools/decode_any.py` 解混淆即可复现上表。

### 根目录脚本

| 文件 | 用途 |
|---|---|
| `reproduce.sh` | 从官方镜像一键复现 `decoded/` 与 `disasm/`，输出与仓库内产物逐字节一致 |
| `tools/build_mn103_objdump.sh` | 自建 GNU objdump 2.45（`--target=mn10300-elf`），产物在 `toolchain/`（已 gitignore） |

### `decoded/`

| 文件 | 说明 |
|---|---|
| `00_0100_402c0020.decoded.bin` | 主体固件代码（MN103） |
| `01_0101_427c0020.decoded.bin` | 语言字符串与字体 |
| `02_0106_43da0020.decoded.bin` | 6-bit 编码区（编码算法仍未解，见下） |
| `03_0104_44000020.decoded.bin` | 8 张 1bpp 文字叠加位图 |
| `manifest.json` | 容器元数据 + 往返校验结果 |
| `strings.jsonl` | 全部可打印字符串（62,167 条，带偏移与运行地址） |
| `leads.jsonl` | 固件/版本/升级相关字符串子集 |

文件名规则：`<块号>_<flags>_<装载地址+0x20>.decoded.bin`。

### `scripts/`

| 文件 | 用途 |
|---|---|
| `oe_container.py` | 容器结构 / 字节普查 / 熵剖面 |
| `part_analysis.py` | 分区头尾分析、LZMA 探测 |
| `payload_profile.py` | payload 结构画像（字节区间分布、16 位值直方图） |
| `record_analysis.py` | 记录步长分析 |
| `record_tables.py` | 解析 16 字节 `(source, length, 0, 0)` 记录表 |
| `crc_and_fields.py` | 头部字段语义 + CRC 穷举（历史过程，已被 sum32 结论取代） |
| `crc_transforms.py` | 字节序/位序变换与 hash 变体（历史过程） |
| `semantic_search.py` | 版本/型号字符串检索 |
| `lens_af_locate.py` | 镜头/AF 相关字符串与结构定位 |
| `xrefs.py` | MN103 绝对寻址交叉引用工具 |
| `get_par.sh` | 从 Wayback 并行分块下载对照机型固件（整文件 GET 会被限流成 4730 B 错误页，须用 Range） |
| `get_one.sh` | 单目标、耐心重试的同类下载器（深度 URL 走 `http://`，`https://` 会间歇性 SSL 失败） |
| `OlympusFw*.hxx` | **Olympus 官方工具源码**——容器格式的权威定义 |
| `EstimateLoadAddress.hxx` | 官方加载地址/字符串扫描辅助 |

### `tools/`

| 文件 | 用途 |
|---|---|
| `oly_container.py` | 容器解析/解混淆（支持 `OE` 与 `OM` 两种块签名），往返校验 |
| `decode_any.py` | 用 `oly_container.py` 解混淆任意机型固件（机型无关） |
| `lens_prefix_chain.py` | 提取「镜头 ID 两字节前缀比较链」的常量集合（跨机型比对用） |
| `maker_code_table.py` | 提取「镜头厂商码比较表」的常量集合 |
| `build_mn103_objdump.sh` | 自建 GNU objdump 2.45（`--target=mn10300-elf`） |

---

## 2026-10-23 新增：解锁落点的确定化 + 社区补丁语义解码

### A. 社区「解锁」补丁的**语义**（首次读出，而非只是字节）

把**已打补丁的** E-M1 III v1.2 块 0 单独导入 Ghidra 并与原版逐指令对照：

```c
/* 原版   */ if (id==6||3||8||9) *p = 0x6cc;
             else if (id==4)     *p = 0x1c20;
             else { 报错 }

/* 补丁后 */ *p = 0x70000010;     /* 无条件 */
```

⇒ **社区改机的「解锁」= 把一个「按模式 ID 取值/分派」的 switch 整体替换成常量返回**
（12 字节**等长**覆盖，不需要移动任何代码）。
这是本项目可复用的**解锁手术模板**。

完整分析：[`evidence/patched_community/unlock_semantics.md`](evidence/patched_community/unlock_semantics.md)

### B. 12/12 个社区归档全部解出，补丁模式表补全

- 阻塞原因：`7zr.exe` **不含 RAR 解码器**；完整版 `7z_full/7z.exe` 才有。
- **模式 A（12 字节）覆盖 9 个机型**，并发现两个比较常量变体：

| 变体 | stock → patched | 机型 |
|---|---|---|
| A1 | `1c a0 06 c8 14 a0 03 c8 10 a0 08 c8` → `fc cc 10 00 00 70 60 88 1c df 80 1c` | E-M1 II v3.0/v3.4、E-M1 III v1.2、E-M5 III v1.4、E-M10 III v1.2、E-PL9 v1.1 |
| A2 | `1c a0 06 c8 0c a0 03 c8 08 a0 04 c8` → `fc cc 10 00 00 70 60 88 1c df 80 08` | E-M10 II v1.3/v1.4、E-M1 v4.6 |

- **模式 B**（`c8 07 → cb cb`）覆盖 8 个机型；**模式 C**（2×2 字节）覆盖 2 个机型。
- **新观察**：E-M10 II v1.3/v1.4 **只有模式 A、没有模式 B** ⇒ A/B/C 是三个独立开关。

完整表：[`evidence/patched_community/community_patch_table.md`](evidence/patched_community/community_patch_table.md)

### C. ★「录像艺术滤镜只 4 项」的落点：类型码 → mask ROM 描述符

| 事实 | 证据 |
|---|---|
| 照片艺术菜单 = 资源 ID `A03F`–`A048`（连续 **10** 项） | 块 1 UTF-16 整池解析 |
| **录像艺术菜单 = 资源 ID `A042`–`A045`（只有 4 项）** | 同上 |
| 菜单项清单在**机身 mask ROM** | 块 0 的「UI 资源描述符表」99 条全部指向 `0x7E…` |
| **但「用哪一份清单」由块 0 的 1 个字节决定** | `mode_state + 0x6B` → `FUN_403ED4B4` 解码成 0..6 规范码 → 6 个平行函数返回**不同**的 mask ROM 描述符 |
| 9 个写入点里**只有 1 个**选到另一张描述符 | `FUN_405731F7` 写 raw `4` → 规范码 2 → `0x7E452BE4`；其余 8 个写 0/2/3 → 规范码 0 → `0x7E452BDC` |

⇒ **★ 单字节补丁位置**：`FUN_405731F7`（`rt 0x405731F7`）末尾的

```c
*(undefined1 *)(param_1[0x18] + 0x6b) = 4;      /* ← 改成 0 即改用另一张描述符 */
```

⇒ **推断**（待实机证实）：把 `4` 改成 `0`，录像艺术滤镜菜单就应从 4 项变成 10 项。

完整分析：[`evidence/art_filter/menu_descriptor_typecode.md`](evidence/art_filter/menu_descriptor_typecode.md)

### D. 艺术滤镜的 ID 体系与菜单资源映射

- **13 个实现模块、两套 ID 命名空间**（任务名里直接带 ID，跨机型跨版本稳定）：
  `art_effect_10/20/30/40/50`（star_light/pinhole/frame/soft_focus/white_edge）
  与 `art_filter_06/09/0E/14/19/1C/1D/21`（rough_monochrome/diorama/gentle_sepia/
  dramatic_tone/artclearline/mirror/composite/pastel_art）。
- 另有 **3 张互不相同的名字集合**：`MODE_EXPOSE_*`（22 项创意模式 + 9 项场景模式）、
  `COLORTONE_*`（12 项艺术滤镜 + 7 项基础色彩模式，**3 份不同顺序**，其中一份是录像侧重排）。
- **滤镜「子 ID → 处理函数」的分派表在 mask ROM `0x7E897CF4`**（16 槽 × 8 字节，
  按 `id & 0xF` 索引）⇒ 块 0 里只有实现，"还有哪些 ID 可用"要靠实机 dump 全知。

完整分析：[`evidence/art_filter/art_filter_menu_and_ids.md`](evidence/art_filter/art_filter_menu_and_ids.md)

### E. AF 修复（2018-12-18 松下镜头）的落点收窄

- 固件自带调试转储把 **`LENS_INFO` 结构逐字段打印**出来 ⇒ 直接得到 20 个子结构
  （`LENS_INFO_AF_CON` / `_IS` / `_LAF` / `_AF` / `_DIST` / `_DISTORTION` / `_SHADING` /
  `_MAKERNOTE` / `_FOURTHIRDS` / `_EZ` / `_PRIVATE` / `_LENS_OIS` / `_ENABLE` /
  `_CHARACTER(_ZM)` / `_STATE` / `_ALL_DATA` / `_CURRENT_CONSUMPTION` / `_RESERVED` …）。
- 每镜头 AF 参数挂在 **`LENS_INFO_LAF.af_data_pos[%d]`**，而周边 6 张表**全部指向 mask ROM**
  ⇒ **参数本体改不了** ⇒ AF 修复只可能是"改代码行为 / 改选哪一组参数"。

完整分析：[`evidence/af_fix_2018/lens_info_af_layout.md`](evidence/af_fix_2018/lens_info_af_layout.md)

---

## 复现

一键复现（校验源文件 → 解混淆 → 往返与校验和验证 → 反汇编）：

```sh
bash reproduce.sh /path/to/OLY_E_108_1800_0000_0000.BIN
# 期望输出：
#   source SHA-256 OK: cc59a4e1…b5cfd
#   roundtrip_identical: True
#   blocks verified: 4/4 (sum32)
```

`reproduce.sh` 生成的 `decoded/` 与 `disasm/` 与本仓库内已提交的产物**逐字节一致**。
固件本体见 [`firmware/`](firmware/)（已收录）或按 [`PROVENANCE.md`](PROVENANCE.md) §2 自行获取。

### 1. 解混淆

```sh
python3 tools/oly_container.py <OLY_E_108_1800_0000_0000.BIN> --out decoded/
# 校验：roundtrip_identical == true，四块 checksum_valid == true
```

### 2. 构建 MN103 反汇编器

系统 binutils 2.38 已移除 mn10300 后端，需自建：

```sh
bash tools/build_mn103_objdump.sh
./toolchain/binutils/objdump --version          # GNU objdump 2.45
./toolchain/binutils/objdump -i | grep mn103    # 需含 mn10300 + binary
```

### 3. 反汇编

```sh
toolchain/binutils/objdump -b binary -m mn10300 -D -z --insn-width=16 \
  --adjust-vma=0x402C0000 --start-address=0x402C0000 --stop-address=0x402C0400 \
  decoded/00_0100_402c0020.decoded.bin
```

`--insn-width=16` 是 MN103 必需项（默认 32 位会错位）。

---

## 已知未解问题（旧版，已被上方 2026-10-22 章节取代）

> ⚠️ 下列「1.8 AF 修复落点在比较链」的结论**已被 2026-10-22 的 v2.2→v2.3 差分证伪**，
> 请以本文档上方「已知未解问题」表格为准。保留原文以留痕。

| 项 | 状态 |
|---|---|
| **1.8 AF 修复的补丁字节** | **落点已收敛到 1 个比较链**：E-P5 1.8 块 0 的「镜头 ID 两字节前缀比较链」`0x403B7989`（7 对 `{C1:80, C1:00, C0:F1, C0:E1, 80:F1, 81:E3, 81:F1}`）。跨机型对照（E-P3 v1.6 同日同修复，链长 4 对）推出**候选补丁字节 = `0xC0F1` / `0xC0E1` 两项**（推断）。仍缺「修复前」基线：Wayback 未存档这 9 个机型的 2018-12-18 之前任何版本（E-P5 v1.7 官方沿革存在但本体未被抓取，官方直链 403），无法做同代码族前后差分。详见报告 §5.5。 |
| **H-ES200 / H-ES50200 的 4 字节镜头 ID** | 未解。固件内无镜头型号名字符串；ID 由镜头经 I²C 应答，型号↔ID 对应表在 mask ROM 或镜头内部。 |
| **块 2 的 6-bit 编码算法** | 未解。该 blob 与 E-PL3(2011) 逐字节相同，属跨代共享资产；E-PL3、E-M1 III、fishcu、oly_fw_tools 四个独立项目均未解开。 |
| ROM 描述符表 `0x7E5558E8` | 位于机身 mask ROM，不在固件镜像内。 |
| E-P5 SoC 全貌 | 本文件只含 1 个 MN103 核的代码；`IMG_CPU0_*` 暗示多核，其余核不在本镜像。 |

---

## 来源与许可

见 [`PROVENANCE.md`](PROVENANCE.md)。

### 本项目原创部分（代码 / 文档 / 证据）

适用 [`LICENSE`](LICENSE)（MIT）。包括：`tools/`、`scripts/`、`docs/`、`evidence/`、
`report/`、`decoded/`、`disasm/`、`reproduce.sh` 及全部中文文档。

### 第三方组件

- `scripts/OlympusFw*.hxx` 与 `scripts/EstimateLoadAddress.hxx` 来自 `cmdada/em10-fw` 内 vendor 的
  Olympus 官方工具 `oly_fw_tools`（用于说明格式定义）。
- `tools/oly_container.py` 来自 `fishcu/oly_fw_analysis`，其实现注明源自 Altsoph / mx3
  （CHDK thread 2471）。
- `tools/ghidra/` 中的 MN10300 SLEIGH 模块基于 `txt231/GhidraMn10300`，
  调用约定补丁与 cspec 参考 `cmdada/em10-fw`。

### ⚠️ 固件本体（`firmware/` 目录）

- `firmware/` 下的 `.BIN` / `.zip` / `.rar` 均为 **Olympus / OM SYSTEM（横滨奥林巴斯 /
  Taiyo Yuden）** 的专有固件与更新产物，**著作权属于原厂，本项目不主张任何权利**。
- 来源：**xdel.ru**（泰语镜像站，含历史版本与社区改机归档）与
  **Wayback Machine** 上的 `ol01.om-digitalsolutions.net` 官方镜像。
- 收录目的：**离线逆向研究、版本对照、备份与互操作分析**。
  **不得**用于商业目的；**不得**用于生成可分发的改机固件。
- 压缩件 `*.BIN.lzma` 为 **LZMA 无损**压缩，与原 `.BIN` 逐字节等价；
  `firmware/MANIFEST.sha256` 同时记录了每个压缩件与**每个原始 `.BIN`** 的 SHA-256。
  验证：`python tools/verify_firmware_bundle.py --deep`（当前 121/121 + 50/50 全部通过）。
- `firmware/community/` 是第三方社区的改机归档，著作权同样属于原厂与社区作者，
  本项目仅作**补丁字节分析**用途。
