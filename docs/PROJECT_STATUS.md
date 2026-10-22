# 项目现状总表（E-P5 固件逆向）

> 更新：2026-10-22
> 仓库：[thrains0220-byte/ep5-fw-reverse](https://github.com/thrains0220-byte/ep5-fw-reverse)（私有）
> 主报告：[`report/逆向分析报告_E-P5_Ver1.8.md`](../report/逆向分析报告_E-P5_Ver1.8.md)
> 方法论：[`RE_METHOD_PLAYBOOK.md`](RE_METHOD_PLAYBOOK.md)

---

## 1. 项目目标

| # | 目标 | 状态 | 备注 |
|---|---|---|---|
| A | 破解 E-P5 1.8 固件容器格式 | ✅ **完成** | 100% 破解，往返逐字节一致 |
| B | 定位 2018-12-18 松下镜头 AF 修复的补丁字节 | ⚠️ **原假设已证伪** | 修复**不在**镜头 ID 结构；落点收窄到"块 0 内既有代码的行为改动" |
| C | 定位艺术（创意）滤镜实现 | ✅ **实现位置与数据流已破解** | 完整地址地图见 `evidence/art_filter/art_filter_address_map.md` |
| D | 定位"解锁录像艺术滤镜"的落点 | ✅ **三个具体落点已定位** | 位掩码 `0x602AEB94` / 分支判定 / 各效果类型白名单 |
| E | 做出"新增创意滤镜"的固件补丁 | 🔶 **方案已定型，未实施** | 模板 A（参数覆盖式）已由伪代码证实可行 |
| F | 实机刷写验证 | ❌ **未做** | 无 E-P5 实机 |
| G | 块 2 的 6-bit 编码 | ❌ 未解 | 四个独立项目均未解 |
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
| 每镜头标定表 | 结构体 `+0x46C` / `+0x48C`，16 字节步长（`FUN_4048B6D2` = 镜头畸变校正） |

### 2.4 艺术（创意）滤镜子系统 ★

| 语义 | 地址 |
|---|---|
| 效果 ID 全局 | `0x605FCD3C`（9 处引用全在 `0x4078844C–0x40789522`） |
| 效果类型全局（拍照/录像） | `0x605FCD40`（值 2 = 拍照） |
| 支持的类型位掩码 | `0x602AEB94` |
| 效果回调指针 | `0x602AEB54` |
| 效果参数区（当前生效） | `0x605FCD44`（312 B） |
| 效果 50 参数模板 | `0x605FCE7C`（312 B，恰好相隔 0x138） |
| 拍照参数区 / ROM 源 | `0x605FCA00` / `0x7E5C9809` |
| 录像参数区 / ROM 源 | `0x605FCCC4` / `0x7E5C9B1C` |
| 效果 ID 设置器 / 复位器 | `FUN_407887E0` / `FUN_40789519` |
| 子系统总初始化 | `FUN_407883DD` |
| 按类型初始化 | `FUN_40788616`（通用）/ `FUN_4078866A`（star_light 专用） |

**效果 ID 空间**：10 `star_light` / 20 `pinhole` / 30 `frame` / 40 `soft_focus` / 50 `white_edge`

**两个新增滤镜模板**：
- **A（参数覆盖式）**：312 B 参数块 + 复用既有效果管线（效果 50 = 效果 10 + 参数覆盖）
- **B（独立式）**：新 ID(60) + 独立参数块 + 独立 pass + 初始化登记

**三个解锁落点**：`0x602AEB94` 位掩码 / `FUN_40788616` 的 `param_1 == 2` 判定 /
各效果初始化函数的类型白名单（star_light 同时处理 type 1 与 type 2 ⇒
"只处理拍照"即被锁形态）。

### 2.5 UI 资源（块 1）

- 块 1 = **UTF-16LE 多语言字符串池**（每条以 UTF-16 NUL 结束），22,937,536 B
- E-P5 照片模式菜单定义（带连续资源 ID）：
  `A03F` Pop Art / `A040` Dramatic Tone / `A041` Soft Focus / `A042` Pale&Light Color /
  `A043` Light Tone / `A044` Grainy Film / `A045` Pin Hole / `A046` Diorama /
  `A047` Cross Process / `A048` Gentle Sepia
- 块 0 内另有 UI 资源 ID 索引表（连续 u16 数组）

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
| 8 | 块 0 存在「ID 索引指针表」 | 唯一命中是 `0x90909090` 填充假阳性 | `find_ptr_tables.py` |
| 9 | 块内字符串可用立即数寻址 | 62,167 条里**只有 1 条**被 `fc <imm32>` 引用 | `Mn103FindArtRefs` |

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
  art_filter/
    art_filter_analysis.md               子系统分析（效果 ID 空间 / pass / 门控 / 否定结论）
    art_filter_address_map.md            ★ 完整地址地图 + 新增滤镜/解锁模板
    art_effect_ids.json                  效果 ID 与函数名清单
    block1_filter_names.json             块 1 UI 名字与资源 ID
    lens_info_table.json                 LENS_INFO 镜头主表
  patched_community/
    community_patch_table.md             ★ 社区改机补丁字节表（3 个通用模式）
    patched_community.json               机器可读补丁表
```

---

## 7. 下一步队列

| 优先级 | 任务 | 状态 |
|---|---|---|
| P0 | 逐个检查 5 个效果的初始化函数 → 产出「哪些滤镜在 E-P5 上被锁、锁在哪条指令」清单 | 🔜 |
| P0 | 按模板 A 实做一个新滤镜的 312 B 参数块，验证落盘方案 | 🔜 |
| P1 | AF 修复：追 12 组每镜头 AF 参数数组（数据区不受重编译影响，差分噪声低） | 🔜 |
| P1 | 块 1 菜单定义表结构 → 确认新增滤镜名字的插入方式（块 1 大小固定） | 🔜 |
| P2 | 解 6 个 RAR 改机归档，补全社区补丁表（需 `unrar` / 7-Zip） | 🔜 |
| P2 | 块 2 的 6-bit 编码 | ⛔ 四项目未解，低优先 |
| P3 | 实机刷写验证 | 需硬件 |

---

## 8. 版权与再分发边界

- 仓库内**不含**任何奥林巴斯固件本体或更新器二进制（仅坐标 / 长度 / SHA-256 / 指令文本）。
- `scripts/OlympusFw*.hxx`、`scripts/EstimateLoadAddress.hxx` 来自 `cmdada/em10-fw` 内的 vendor
  Olympus 官方工具 `oly_fw_tools`（仅用于说明格式定义）。
- `tools/oly_container.py` 来自 `fishcu/oly_fw_analysis`（其实现注明源自 Altsoph / mx3，
  CHDK thread 2471）。
- 本项目原创：其余 `tools/*.py`、`tools/ghidra/*.java`、`docs/`、`evidence/` 全部产物。
- 第三方引用见 [`PROVENANCE.md`](../PROVENANCE.md)。
