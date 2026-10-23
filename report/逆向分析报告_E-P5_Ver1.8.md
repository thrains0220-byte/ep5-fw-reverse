# 奥林巴斯 PEN E-P5 固件 (Ver. 1.8) 逆向分析报告 v2

**目标**：`E-P5_固件_1.8/OLY_E_108_1800_0000_0000.BIN`
**SHA-256**：`cc59a4e13b3bf6c46405bd396975cb9c93a7634b7a4a36822259b1fc498b5cfd`
**大小**：44,826,624 字节 (0x2AC0000)
**工具链**：REA 6.4.0 (CLI) + Binwalk 3.1.0 + Unblob 26.6.4 + 自建 GNU objdump 2.45 `mn10300-elf`
**交叉验证源**：
- **Olympus 官方工具源码** `oly_fw_tools`（`OlympusFwBlockHeadTail.hxx` / `OlympusFwScramble.hxx` / `OlympusFwChecksum.hxx` / `OlympusFwConstants.hxx`）
- `fishcu/oly_fw_analysis` → `tools/oly_container.py`（Altsoph / mx3 / CHDK thread 2471 实现）
- `cmdada/em10-fw`（MN103 模拟器 + `mn10300.igen` SLEIGH 规范 + ISA 手册 `olympus_cpu_isa_13250-040e.pdf`）
- `sympho-ru/olympus-e-pl3-research`（E-PL3 同容器谱系 + 53,425 条已验证 MN103 指令 + 逐段 SHA-256）

> **v2 相对 v1 的变化**：容器格式不再是"逆向推断"，而是**与 Olympus 自家源码逐字段对齐**；ISA 已确认为 **MN103**；`flags` 字段语义、`loadingAddress` 端序、校验和算法全部修正；新增内存映射表、`LENS_INFO` 结构体布局、跨代哈希比对等章节。

---

## 0. 结论摘要

| # | 结论 | 证据强度 |
|---|---|---|
| 1 | `.BIN` 是 **Olympus「OE」混淆块容器**，4 个块，每块 32B 头 + payload + 32B 尾 | **官方源码 + 逐字节往返一致** |
| 2 | 头部 32 字节全部字段已与 Olympus 官方 `BlockHeadTail` 结构体**逐字段对齐** | **官方源码** |
| 3 | `flags` 语义：`0x0100`=主控代码 / `0x0101`=多语言+字体 / `0x0104`=图片/文字叠加 / `0x0106`=内容域 [0x00;0x3F] | **官方源码** |
| 4 | payload 混淆 = **16 字节内 16 列字节置换 + 全字节 XOR 0xFF** | **官方源码 + 往返一致** |
| 5 | 尾部校验 = **加法 sum32**（`-Σ(u32 LE)`），**不是 CRC32** | **官方源码** |
| 6 | 块 0 指令集 = **Panasonic MN1030/MN103S**（16 位 RISC，小端） | objdump 实证 + E-PL3 谱系 + 官方 ISA 手册 |
| 7 | 块 2 的 6-bit 区与 **E-PL3(2011) 逐字节完全相同**（SHA-256 `93c4e558…`） | 逐段哈希比对 |
| 8 | 机身内存映射（8 个区域）已从块 0 反汇编还原 | objdump 实证 |
| 9 | `LENS_INFO` 结构体 **25 个字段的字节偏移**已还原 | objdump + 标签表索引对齐 |
| 10 | PC 端更新器**不解析 OE 容器**，容器由机身 bootloader 解析 | 全二进制魔数搜索 0 命中 |

**一句话**：容器层 100% 破解；代码层已具备完整 MN103 反汇编能力并定位到镜头子系统；1.8 版 AF 修复的**补丁字节**仍未逐字节定位（见 §8）。

---

## 1. 容器格式完整规格

### 1.1 官方结构体（Olympus `OlympusFwBlockHeadTail.hxx`，逐字引用）

```c
#pragma pack(push)
#pragma pack(1)
struct BlockHeadTail
{
	byte typeSig[2];      // 0x00 "OE"
	byte modelSig[2];     // 0x02 机型码
	byte zeroPadding1[4]; // 0x04 镜头固件此处置 0/1/2
	uint32_t loadingAddress; // 0x08
	uint32_t len;         // 0x0C  payload 长度
	uint16_t version;     // 0x10
	byte zeroPadding2[2]; // 0x12
	uint16_t flags;       // 0x14
	byte zeroPadding3[6]; // 0x16
	uint32_t checksum;    // 0x1C
};
#pragma pack(pop)
```

**我先前独立推导出的字段偏移与官方结构体 100% 一致**（`+0x0E` 那次是我按 64KiB 块反推的等价表述；官方是 `+0x0C` 的 u32 `len`）。

### 1.2 四个块的实际取值

| # | 容器偏移 | `len` | `loadingAddress` | `version` | `flags` | 官方含义 |
|---|---|---|---|---|---|---|
| 0 | `0x00000000` | 15,728,576 | `0x402C0000` | `0x1800` | `0x0100` | **主控 MCU 代码** |
| 1 | `0x00F00000` | 22,937,536 | `0x427C0000` | `0x0000` | `0x0101` | **多语言字符串 + 字体** |
| 2 | `0x024E0000` | 2,490,304 | `0x43DA0000` | `0x0100` | `0x0106` | 内容域限定 [0x00;0x3F] |
| 3 | `0x02740000` | 3,669,952 | `0x44000000` | `0x0100` | `0x0104` | **图片（照片文字叠加）** |

- `typeSig` = `OE` → 官方枚举 `BLK_OE` = *"E-system body firmware, main microcontroller"*
- `modelSig` = `10 80` → `sig2int()` 后 = **0x1080 = E-P5**
- `version` = `0x1800` → **Ver. 1.8**（与文件名 `OLY_E_108_1800_0000_0000` 的编码规则吻合）

### 1.3 混淆算法（官方 `OlympusFwScramble.hxx`）

```
1) 16 字节为一组做字节置换：
   Decoded seq: 0123 4567 89ab cdef
   Encoded seq: 2031 5746 ba98 ecdf
2) 全部字节 XOR 0xFF
```
（因 XOR 与置换可交换，官方实现是先置换后 XOR；`descramble` 逆序等价。）

**官方还给出了另一套容器**：`BlockTailSFile`（用于 `Smmmvvvv.BIN` 服务/维修卡包），尾部布局完全不同。本文件走 `BlockHeadTail`。

### 1.4 校验和（官方 `OlympusFwChecksum.hxx`）

```
datasum = Σ(data 按 u32 LE 分组)   (32 位回绕)
checksum = -datasum
```
作用范围 = **块头 + 反混淆后的 payload + 尾部（末 4 字节校验和置 0）**。

> **更正 v1**：我此前写成"CRC32 校验尾"，并穷举了 CRC32/CRC32C/BZIP2/MPEG-2/POSIX/JAMCRC/KOOPMAN/XFER/AUTOSAR/CRC32D/Adler32 等十余种算法全部落空——真正原因是它**根本不是 CRC**。

### 1.5 验证

- 参考实现对 E-P5 跑出 `roundtrip_identical: true`（`decode → encode` 与源文件 SHA-256 完全相同）
- 4 个块 `checksum_valid: true`
- 官方 `computeChecksum` 逐块复算一致

---

## 2. 指令集识别：MN1030 / MN103S

### 2.1 判定链

| 证据 | 内容 |
|---|---|
| 官方 ISA 手册 | `em10-fw/tools/olympus_cpu_isa_13250-040e.pdf` = **MICROCOMPUTER MN1030/MN103S Instruction Manual**（Pub.No.13250-040E，松下 Matsushita） |
| Ghidra SLEIGH 规范 | `emu/isa/mn10300.igen`（含 `mn10300` / `am33` / `am33_2` 三模型） |
| 容器谱系 | E-PL3(2011) 与 E-M1 III(2020) 的块 0 同为 **MN103 主固件**；E-P5(2013) 同代同谱系 |
| 实证反汇编 | `objdump -m mn10300 --insn-width=16` 对 E-P5 块 0 输出**连贯可读的真实代码** |

### 2.2 关键编码参数（由 GDB `mn10300.igen` + `emu.h` 确认）

- 指令宽度 **16 位**，小端
- 立即数端序：`FETCH32(a,b,c,d) = a + (b<<8) + (c<<16) + (d<<24)` → **小端**
- `mov imm32,Dn` = `FC Cx` + imm32（6 字节）；`mov imm32,An` = `FC Dx` + imm32（6 字节）
- `mov imm16,An` = 3 字节；`mov imm8,Dn` = 2 字节；`mov Dm,Dn` = 1 字节
- 特殊寄存器窗口 `0x8000–0x8FFF`（`emu.h`: `sysreg[0x800]`）
- 扩展单元浮点指令由 Olympus 自行扩展（`emu/isa/em10.igen`，`udf02/03/04/05/06`）

### 2.3 反汇编管线（本机自建）

系统 binutils 2.38 已移除 mn10300 后端，故按 E-PL3 项目的方法自建：

```sh
../binutils-2.45/configure --target=mn10300-elf \
  --disable-nls --disable-werror --disable-gdb --disable-sim --disable-gas \
  --disable-ld --disable-gprof --disable-gold --disable-libctf \
  --with-system-zlib --disable-shared
make all-binutils
```
> 注：configure 需显式 `--build=x86_64-pc-linux-gnu`，否则 `config.sub` 探测会报 "too many arguments"。

用法（`--insn-width=16` 是 MN103 必需项）：
```sh
mn10300-objdump -b binary -m mn10300 -D -z --insn-width=16 \
  --adjust-vma=0x402C0000 --start-address=... --stop-address=... block0.bin
```

**入口点 `0x402C0000` 反汇编（真实启动代码）**：
```
402c0000: and  61695,psw
402c0004: nop
402c0006: add  -4,sp
402c0009: calls 0x402c00e5
...
402c007c: mov  2115043360,d3      ; 0x7E110020
402c0082: movhu d3,(0x8000)        ; ← 写 MN103 特殊寄存器
402c0085: mov  2115043400,d3      ; 0x7E110048
402c008b: movhu d3,(0x8004)
```

---

## 3. 机身内存映射（从块 0 反汇编还原）

`0x402F8800` 处是一段 `mov imm32,d0` 序列，构成 **8 个存储区域**的描述表：

| 描述符地址 | 基址 | 对应 |
|---|---|---|
| `0x402F8807` | `0x40100000` | ROM 区（boot / mask ROM） |
| `0x402F881A` | `0x40120000` | ROM 区 |
| `0x402F882D` | `0x402C0000` | **块 0**（主控代码，末尾 `0x411BFFC0`） |
| `0x402F8840` | `0x411C0000` | 块 0 之后的首个区域 |
| `0x402F8853` | `0x427C0000` | **块 1**（语言/字体） |
| `0x402F8866` | `0x43DA0000` | **块 2**（6-bit 区） |
| `0x402F8879` | `0x44000000` | **块 3**（叠加位图） |
| `0x402F888C` | `0x45A00000` | 末区 |
| `0x402F88FC` | `0x00000001` | 条目数/标志 |

另外代码中还会引用 `0x60xxxxxx`（数据区，如 `0x60345AEC`、`0x604452C0`）与 `0x7Exxxxxx`（**机身 ROM 区，不在固件镜像内**）两个地址空间。

---

## 4. 四个块的数据结构

### 4.1 块 1 —— 多语言字符串 + 字体（flags `0x0101`）

- 头部 **64 条** 16 字节记录 `(source u32, length u32, 0, 0)`
- 数据区起点 = **0x7E0**（表尾到 0x400 之间是零填充；与 E-PL3 的 `0x7e0` 完全一致）
- 每条记录的 `source` 即该数据镜像的运行地址，`source - 0x427C0020` = 块内偏移
- 数据镜像**无缝平铺**：`addr[i+1] = addr[i] + len[i]`
- 镜像内容示例（rec1）：**UTF-16LE** 字符串 —— `32 00 35 00 40 00 52 00 45 00 43 00` = `"25@REC"`、`"MF"`、`"RA"` …

### 4.2 块 2 —— 6-bit 编码区（flags `0x0106`）

- 前 8 字节：`(size u32 = 0x00240000, addr u32 = 0x43DA0400)`，其余 `0xFF` 填充到 **0x3E0**
- `0x3E0`（= 段起点 +0x400）起 **0x240000 字节**载荷，尾部再 `0xFF` 填充到块尾
- 载荷字节值域 **[0x00;0x3F]，唯独缺 0x3C**（0x3C 疑为转义/标记码）——与官方 flags 注释"all bytes in range [0x00;0x3F]"完全吻合

**跨代哈希比对（关键发现）**：

| 区段 | 长度 | E-P5 SHA-256 | E-PL3(2011) SHA-256 | 结果 |
|---|---|---|---|---|
| off 0 | 8 | `5172fd5b…` | `fbfeb9ce…` | 不同（仅装载地址 `0x43DA0400` vs `0x43D00400`） |
| off 8 | 984 | `8b147211…` | `8b147211…` | **完全相同** |
| off 992 | 2,359,296 | `93c4e558…` | `93c4e558…` | **完全相同** |
| off 2360288 | 130,016 | `255cf8d8…` | `255cf8d8…` | **完全相同** |

→ 该 6-bit blob 是**跨代共享资产**（2011 E-PL3 → 2013 E-P5 原样携带），**不是 E-P5 专属数据**。
→ **推论：1.8 的 AF 修复不可能在块 2 里**，这一方向被排除。
→ 该编码至今未被任何人解开（E-PL3 项目与 E-M1 III 项目均标记为开放问题）。

### 4.3 块 3 —— 照片文字叠加位图（flags `0x0104`）

- 索引表：8 条 `(source, length, 0, 0)` @ `0x00`，其余为零填充到 `0x3E0`
- 数据起点 `0x3E0`，8 张 1bpp 位图，逐张之间有 0x200 间隙
- 每张头部形如 `00 01 00 00 | ff db | 00 43 | 01 01 01 …`（宽度 256 等）
- 块内含字符集表 `%&'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz`（非完整 ASCII → 叠加文字字模索引）

---

## 5. 镜头子系统（1.8 AF 修复的落点区域）

### 5.1 `LENS_INFO` 结构体布局（**已还原**）

调试输出把 25 个字段标签按序打印出来；代码按 ROM 描述符表 `0x7E5558E8 + k*0x10` 取标签，与字段序号**严格对齐**，由此定出字节偏移：

| 序 | 字段 | 字节偏移 | 序 | 字段 | 字节偏移 |
|---|---|---|---|---|---|
| 000 | `LENS_INFO_STATE` | a2+2 | 012 | `LENS_INFO_AF` | a3+50 |
| 001 | `LENS_INFO_CHARACTER` | a2+4 | 013 | `LENS_INFO_AF_CON` | a3+52 |
| 002 | `LENS_INFO_CHARACTER_ZM` | a2+6 | 014 | `LENS_INFO_DIST` | a3+54 |
| 003 | `LENS_INFO_RESERVED` | a2+8 | 015 | `LENS_INFO_SYNC` | a3+56 |
| 004 | **`LENS_INFO_MAKERNOTE`** | **a2+10** | 016 | `LENS_INFO_DIST_PARAM` | a3+58 |
| 005 | `LENS_INFO_SHADING` | a2+12 | 017 | `LENS_INFO_LIFTM` | a3+60 |
| 006 | `LENS_INFO_DISTORTION` | a2+14 | 018 | `LENS_INFO_WOB_MAG` | a3+70 |
| 007 | `LENS_INFO_FOURTHIRDS` | a2+16 | 019 | `LENS_INFO_WOB_POSSIBLE` | a3+72 |
| 008 | **`LENS_INFO_AF_CON`** | **a3+42** | 020 | (未命名) | a3+74 |
| 009 | `LENS_INFO_IS` | a3+44 | 021 | `LENS_INFO_3D` | a3+76 |
| 010 | `LENS_INFO_LAF` | a3+46 | 022 | `LENS_INFO_EZ` | a3+78 |
| 011 | `LENS_INFO_LAF_CON` | a3+48 | 023 | `LENS_INFO_PRIVATE` | a3+80 |
| | | | 024 | `LENS_INFO_PRIVATE_STATE` | a3+82 |

要点：
- 结构体**分成两段**（`a2` 段 0–7、`a3` 段 8–24），与固件里同时存在的 `LENS_INFO` / `LENS_INFO_MAKERNOTE_A` / `LENS_INFO_FOURTHIRDS_A` 等"带 `_A` 后缀"的第二套布局相符
- `LENS_INFO_MAKERNOTE`（**厂商备注**）位于 `a2+10` —— 这正是区分松下镜头与奥林巴斯原厂镜头的关键位
- `LENS_INFO_AF_CON`（对焦连续性参数）出现两处（`a3+42` 与 `a3+52`），全块内被访问 **52 次**，是热点字段

### 5.2 AF 调校数据数组

调试输出列出 12 个命名数组 + `af_data_pos[%d]`：

```
af_data_pos[%d]
vh.af_c[%d]   vh.af_u_d[%d]   vh.af_l_r[%d]
vl.af_c[%d]   vl.af_u_d[%d]   vl.af_l_r[%d]
vv.af_c[%d]   vv.af_u_d[%d]   vv.af_l_r[%d]
hk.af_c[%d]   hk.af_u_d[%d]   hk.af_l_r[%d]
```
`af_u_d` = 上/下方向，`af_l_r` = 左/右方向，`af_c` = 中心；`vh/vl/vv/hk` 为四组方向/模式分类。
另有 `af_judge = %x`、`LENS_INFO_SIZE`、`LENS_INFO_CONFDATA`、`lens_firmup_header`、`Lens_Firm_Version %x`。

### 5.3 镜头也有自己的固件

`LENS_FIRM_UP`、`g_lens_firmup_header`、`STB FIRM UP header_maker / header_fw / maker_code / fw_type / id / hw…`，
`[lens] IS update error!`，`[IOE]SET_MAKER_ID:`。

### 5.4 1.8 AF 修复的定位结论（第一版）

- 修复**不在块 2**（已用跨代哈希排除）
- 修复**不在块 1/块 3**（语言字体与叠加位图，无 AF 语义）
- 修复**必然在块 0**，且最可能的落点是：
  1. `LENS_INFO_MAKERNOTE`（`a2+10`）的**厂商分支**——按厂商码选择 AF 参数
  2. `LENS_INFO_AF_CON`（`a3+42` / `a3+52`）的**填充逻辑**
  3. `vh/vl/vv/hk` × `af_c/af_u_d/af_l_r` 的 **AF 调校数据表**
- 反汇编已确认 `0x402CF1E1` 处有**按 `LENS_INFO_STATE` 字节（结构体 offset 0）跳转的状态机**，`0x402C21C2` 有 `movhu (42,a2),d3`（读 AF_CON）
- **尚未完成**：把"厂商码 → AF 参数"的那段分支逐字节定位并给出补丁字节。这需要继续沿 `a2+10` 的读取点回溯 maker 比较常量。

### 5.5 第二轮：镜头 ID 识别代码测绘 + 跨机型对照（新增）

本节全部是**静态反汇编观察**，不含任何执行/刷机证据。配套数据见
`evidence/af_fix_2018/`（跨机型 JSON、官方版本沿革 JSON、两条链的反汇编快照）。

#### 5.5.1 官方修复文本与机型范围

E-P5 官方更新说明（本地留存 `官方固件更新说明_E-P5_Ver1.8.html`）：

> Ver.1.8 (Dec.18 2018) — Corrected issue of autofocus (AF) function not operating correctly
> when using the "H-ES200" and "H-ES50200" interchangeable lens produced by Panasonic.

从 Wayback 取回的**官方发布说明页**重建了 28 个型号的完整版本沿革
（`evidence/af_fix_2018/model_release_history.json`）。其中 **17 个型号**的说明页含同一句
H-ES200/H-ES50200 条目：

| 型号目录 | 机型 | 含该条目的版本 | 日期 |
|---|---|---|---|
| 0850 | E-P3 | v1.6 | Dec.18 2018 |
| 0860 | E-PL3 | v1.6 | Dec.18 2018 |
| 0870 | E-PM1 | v1.6 | Dec.18 2018 |
| 0970 | E-M5 | v2.3 | Dec.18 2018 |
| 1000 | E-PL5 | v1.6 | Dec.18 2018 |
| 1010 | E-PM2 | v1.6 | Dec.18 2018 |
| 1080 | **E-P5** | **v1.8** | **Dec.18 2018** |
| 1120 | E-PL6 | v1.4 | Dec.18 2018 |
| 1130 | E-M10 | v1.4 | Dec.18 2018 |
| 1090 | E-M1 | v4.4 起 | Feb.28 2018 |
| 1180 | E-M5 Mark II | v4.0 起 | Feb.28 2018 |
| 1220 | PEN-F | v3.0 起 | Feb.28 2018 |
| 1250 | E-M1 Mark II | v2.0 起 | Feb.28 2018 |
| 1150 | E-PL7 | v1.4 | May.10 2018 |
| 1200 | E-M10 Mark II | v1.3 | May.10 2018 |
| 1260 | E-PL8 | v1.1 | May.10 2018 |
| 1300 | E-M10 Mark III | v1.1 | May.10 2018 |

**未列入**该条目的机型（可作对照基线）：1330 E-PL9、1340 E-M1X、1370 E-M5 Mark III、
1390 E-M1 Mark III、1400 E-M10 Mark IV、1420 E-P7、1430 OM-1。

**关键否证（观察）**：E-P5 **v1.7 (Jan.28 2016) 确实存在**于官方版本沿革，但 Wayback 的
`dl01.om-digitalsolutions.net` 全量 CDX（157 条）中 E-P5 只有一个 `.BIN`（即 1.8 本体），
官方直链对固件目录一律 403（CloudFront 签名失效，返回 XML `MissingKey`）。
**⇒ 无法获得 E-P5 1.7 本体，同机型版本差分路线被证据性排除**（不是"没找到"，是"确认未存档"）。

#### 5.5.2 E-P5 1.8 镜头 ID 识别代码（逐指令确认）

镜头记录结构（由 `0x403B7AF8` 的 maker 分派与 `0x403B7B9A` 的填充逻辑还原）：

- 记录指针由 `(12,sp)` 传入
- **4 字节镜头 ID 位于记录 +14..+17，大端序**（`0x403B79FC` 处 `asl 24/16/8 + or` 拼成 u32 交给 printf）
- 厂商码（`LENS_INFO_MAKERNOTE`）位于记录 **+10**（`movhu (10,a2),d0`）

三张表 / 一条链：

| 位置 | 内容 | 说明 |
|---|---|---|
| `0x403B5ACF` | **镜头厂商码表**，10 项 `0xB0 0xB1 0xB2 0x70 0xC0 0xC1 0xC2 0xC3 0x80 0x81` | 取记录+10 的字节与之比较；命中则把该码写入全局 `0x9A400014` 并置 `0x9A40001C` |
| `0x403B7989` | **镜头 ID 两字节前缀比较链**，7 对 `{0xC1:0x80, 0xC1:0x00, 0xC0:0xF1, 0xC0:0xE1, 0x80:0xF1, 0x81:0xE3, 0x81:0xF1}` | 按 ID 的**高两字节**比较（`movbu (14,a2)` / `movbu (15,a2)`）；命中→跳过"未知镜头"告警；未命中→把 4 字节 ID 拼成 u32 交给 printf（格式串在 mask ROM `0x7E43018C`） |
| `0x403B7C1D` | 第二条链，3 对 `{0xC1:0x80, 0xC1:0x00, 0x81:0xE3}` | 命中→取全局 `0x60533AEC`（`0x403BA6A0`）写入记录 +18 |
| `0x403B825D` | 50 槽 / 4096 B **镜头 ID 历史环形队列** | 每次识别到已知镜头就把 4 字节 ID 入队；哨兵值 `27888` 表示"无镜头" |

链的开关字在 `0x605339A0`：**bit1 = 启用白名单检查**、**bit2 = 强制走"未知镜头"路径**、
bit4 = 记录镜头 ID 到历史队列。初始化时 `0x403B78CA` 把它置为 `4`（即 bit2）。
比较链按**厂商码降序**排列（C1 → C0 → 81 → 80），说明它是一张**有序的按厂商分组的表**。

**否证（观察）**：E-P5 1.8 块 0 内共 **20 处**出现"把 4 字节镜头 ID 组装成 u32"的指令序列
（`asl 24/16/8` + `or`），逐处检查其后的比较指令，**没有任何一处把该 u32 与立即数比较**
（最近似的一处只与 `0x1400F001` 这样的格式串常量有关）。
**⇒ 1.8 补丁不是 4 字节镜头 ID 级的比较，而是两字节（厂商码 + 型号码）前缀级的。**

#### 5.5.3 跨机型对照（6 个固件，全部自行下载并通过容器往返校验）

| 机型 / 固件 | 块 0 基址 | 前缀链 | 厂商码表 |
|---|---|---|---|
| **E-P5 1.8**（含修复） | `0x402C0000` | **7 对**（`0x403B7965`） | 10 项（`0x403B5ACF`） |
| **E-P3 1.6**（含修复） | `0x402C0000` | **4 对**（`0x403EFBC5`） | 10 项（`0x403EDCCD`） |
| E-M10 1.4 | `0x40300000` | 无 | `{B0,70,C0,80}` + `{B0,B1,B2,70}` |
| E-M10 III 1.2 | `0x406E0000` | 无 | 同上 |
| E-M5 III 1.1 | `0x40780000` | 无 | 同上 |
| E-M1X 2.1 | `0x407E0000` | 无 | 同上（另有一张 14 项表） |

观察与推断：

1. **该前缀链只存在于 2012/2013 代代码库**（E-P5 / E-P3 / E-M5 / E-PL3 一脉）；
   2014 代及以后（E-M10 / E-M10 III / E-M5 III / E-M1X）**结构被重写**，既没有这条链，
   厂商码表也被拆成两张更小的表。⇒ 想对表必须回到 2012/2013 代代码库。
2. **E-P3 v1.6 与 E-P5 1.8 的这个函数逐指令同构**（同样的门控位、同样的比较链骨架、
   同样的"拼 4 字节 ID 交给 printf"的收尾），**唯一差别是链长 4 对 vs 7 对**，
   且 E-P5 多出的 3 对全部追加在链尾（厂商码 0x80 / 0x81）。反汇编快照：
   `evidence/af_fix_2018/lens_prefix_chain_{E-P5_1.8,E-P3_1.6}.txt`。
3. **两张厂商码表在 E-P5 1.8 与 E-P3 v1.6 中完全相同**（同样 10 项、同样顺序）。
   ⇒ 若补丁动的是厂商码表，两机型必然被改成同样内容。
4. E-P3 v1.6 的**第二条链与 E-P5 1.8 完全不同**（E-P3 是 `{C1:80, C1:00}` + 一个 0x60 厂商组，
   E-P5 是 `{C1:80, C1:00, 81:E3}`）⇒ 第二条链是**机型自有列表**，不是补丁落点。

#### 5.5.4 补丁字节级假设（**推断**，尚待基线验证）

**可严格推出的部分：**

1. 1.8 补丁是**同一天、同一句文案**下发给 9 个 2012/2013 代机型
   （E-P3 / E-PL3 / E-PM1 / E-M5 / E-PL5 / E-PM2 / E-P5 / E-PL6 / E-M10）。
   ⇒ 补丁在**每个**机型的同一张表里做**同样的改动**。
2. 该表就是 §5.5.2 的前缀比较链（两机型逐指令同构、只有链长不同）。
3. 补丁针对**两支镜头**（H-ES200 与 H-ES50200）⇒ 很可能**各占 1 项**。
   - E-P3 v1.6 链 = 4 项 ⇒ 补丁前 2 项
   - E-P5 1.8 链 = 7 项 ⇒ 补丁前 5 项
   - 两机型的**交集** `{0xC1:0x80, 0xC1:0x00, 0xC0:0xF1, 0xC0:0xE1}` 必含补丁加入的那 2 项
   - E-P5 链尾多出的 `{0x80:0xF1, 0x81:0xE3, 0x81:0xF1}` 属 E-P5 机型自有（补丁前就存在）
4. 补丁**没有新增厂商码**（否则 E-P5 1.8 与 E-P3 v1.6 的 10 项厂商码表不可能仍然完全相同，
   除非新增的那个码恰好与既有码合并）。⇒ 补丁新增的 2 项**沿用既有厂商码**。
5. 链按厂商分组排列（E-P5：0xC1 组 2 项 → 0xC0 组 2 项 → 0x80 组 1 项 → 0x81 组 2 项），
   2 项必属**同一厂商组**。⇒ 候选只剩两组：

| 候选 | 新增的 2 项 | 厂商码 | 补丁前 E-P3 链 | 补丁前 E-P5 链 |
|---|---|---|---|---|
| A | `0xC1:0x80` + `0xC1:0x00` | 0xC1 | `{0xC0:0xF1, 0xC0:0xE1}` | `{0xC0:0xF1, 0xC0:0xE1, 0x80:0xF1, 0x81:0xE3, 0x81:0xF1}` |
| B | `0xC0:0xF1` + `0xC0:0xE1` | 0xC0 | `{0xC1:0x80, 0xC1:0x00}` | `{0xC1:0x80, 0xC1:0x00, 0x80:0xF1, 0x81:0xE3, 0x81:0xF1}` |

6. **倾向 B（`0xC0F1` / `0xC0E1`）**，理由：
   - 第二条链（`0x403B7C1D`）在 **E-P5 1.8 与 E-P3 v1.6 中都恰好包含 `{0xC1:0x80, 0xC1:0x00}`**，
     而**都不包含** `{0xC0:0xF1, 0xC0:0xE1}`。第二条链是"需要额外参数"的子集 ⇒
     `{0xC1:0x80, 0xC1:0x00}` 是**补丁前就有**的老条目，补丁新增的更可能是"普通条目"。
   - 松下/徕卡镜头只有 2 款且共享厂商码，落在一个**连续的新增组**里更自然。

**补丁字节的精确形态**（若候选 B 成立，插入 `0x403B7989` 链中 0xC0 组位置，两块约 28 B）：

```
f0 40            movbu (a0),d0        ; 镜头 ID 高字节
2d c0 00         mov  192,d1          ; 厂商码 0xC0
a4               cmp  d1,d0
c9 0b            bne  +11
f8 42 0f         movbu (15,a2),d0     ; 镜头 ID 次字节
fa c8 f1 00      cmp  241,d0          ; 型号码 0xF1   ← 补丁字节
c8 6b            beq  +107
```

**验证缺口（诚实）**：要最终在 A / B 之间定案，需要 2018-12-18 **之前**、且属于
2012/2013 代代码库的固件（补丁前的链长应为 E-P3 2 项 / E-P5 5 项）。
Wayback 存档里这 9 个机型的早期版本**一个都没有**（已逐一核对 CDX）；
官方直链对固件目录一律 403（CloudFront 签名失效）。
现存的 2011–2014 老机型（0420/0450/0480/0350/0360/0680/0700/0790）属 4/3 代或更早的代码库——
已实测 0480 v1.3.1（基址 `0x40040000`，无前缀链、无厂商码表）**不承载这张表**，无法充当基线。

#### 5.5.5 本轮新增的否证结论（诚实边界）

- 固件内**不存在**任何镜头型号名字符串（`H-ES200` / `H-ES50200` / `M.ZUIKO` / `40-150` 均无命中；
  块 1 里的 `FCON-P01` / `WCON-P01` / `MCON-P01` / `MAL-1` / `11mm` / `14-42mm II R` 是转接附件名），
  ⇒ **无法从固件直接读出镜头 ID 与型号名的对应表**。
- 镜头 ID 是通过 I²C 向**镜头本身**读取的（`LENS_ASKDATA_MODE_*` / `LENS_INFO_AF_CON` 等
  34 个字段由镜头应答），相机侧的"每镜头 AF 参数表"在 **mask ROM**，不在固件镜像内
  ⇒ **补丁不可能是"新增镜头表条目"**，只能是固件代码或固件内参数表。
- E-P5 1.8 的 AF 调校数据（`wob_amp_max[%d]` / `ap_speed_max[%d]` / `ap_speed_sil[%d]` /
  `.prm.lv.{fcs_act_mode, ap_target, ap_speed, wob_amp, …}`）**未见任何按镜头 ID 索引的痕迹**，
  索引维度是模式而非镜头 ⇒ 若补丁落在这里，则必然是"按厂商码分支"，与 §5.5.2 的前缀链结论一致。

---

### 5.6 第三轮：v2.2→v2.3 同机型差分 —— 证伪"落点在镜头 ID 结构"（2026-10-22 新增）

配套证据：`evidence/af_fix_2018/af_fix_v22_v23_negative_result.md`。

**新基线的来源**：xdel.ru（此前未被利用的镜像）提供了 **E-M5 v2.0 / v2.1 / v2.2**
三个"修复前"版本。E-M5 与 E-P5 同为 2012 代机身、同一代代码库，
且 E-M5 v2.3 与 E-P5 v1.8 **同日（Dec.18 2018）下发同一条修复文案**。

| 结构 | E-M5 v2.2（修复前） | E-M5 v2.3（含修复） | 结论 |
|---|---|---|---|
| 前缀比较链 | 7 项 `C1:80 C1:00 C0:F1 C0:E1 80:F1 81:E3 81:F1` | **完全相同** | 修复**不在**比较链 |
| LENS_INFO 镜头主表 | 106 条 / 105 个唯一 ID | **完全相同** | 修复**不在**镜头主表 |
| 厂商码分组 | 13 组 | **完全相同** | 同上 |

字节级差分不可用（两版块 0 长度相同但 **3,319,143 字节不同**、349,129 个跨度，
三年间整包重编译并重排），故采用**结构化语义对照**。

⇒ **§5.5.4 的候选补丁字节（`0xC0F1` / `0xC0E1`）被证伪。**
剩余方向：AF 控制流程、每镜头 AF 参数组（§5.2 的 12 个命名数组 +
`af_data_pos[%d]`）、镜头 I²C 应答处理（`LENS_ASKDATA_MODE_*`）。

旁证：`cmdada/em10-fw` 的 `notes/autofocus.md` 描述机身侧**约 12 组每镜头 AF 参数块**
（`fcs_act_mode, ap_target, ap_speed, wob_amp, wob_move, ofs_time, ofs_move,
iaf_target, iaf_speed, iaf_dist`）——"新增一个松下镜头组"正是该类修复会做的事。

### 5.7 第三轮：LENS_INFO 镜头主表（新增）

配套证据：`evidence/art_filter/lens_info_table.json`（由 `tools/lens_table.py` 生成）。

块 0 数据段存在一张**镜头主表**，8 字节记录
`{uint16 category, uint16 slot, uint8 maker, uint8 model, uint16 extra}`，
其中 `maker:model` 即 4 字节镜头 ID 的高两字节。定位依据：
字符串 `"LENS_INFO SIZE"` 之前、ASCII 字符串区起点处的连续合法记录。

- E-P5 1.8：表起点 `0x405E8EE0`，**106 条记录 / 105 个唯一镜头 ID**
- E-M5 2.3：同一张表（结构与内容一致），起点 `0x404A A...?`（同构）

厂商码分组（两机型相同）：
`60`(5) `70`(8) `80`(1) `81`(2) `B0`(14) `B1`(15) `C0`(14) `C1`(24) `C2`(3) `C3`(1) `D0`(3) `D1`(10) `E0`(1)

---

### 5.8 第四轮：双机型复现 + 全块差分（2026-10-22 新增）

配套证据：`evidence/af_fix_2018/af_fix_block_scope.md`。

**第二组前后对照**：xdel.ru 的 `pre_fix/` 另提供 **E-PM2 v1.1/v1.2/v1.3/v1.4/v1.5** 五个修复前版本。
E-PM2 v1.5 → v1.6 的镜头识别结构对照结果与 E-M5 v2.2 → v2.3 **完全一致**
（比较链 7 项相同、LENS_INFO 106 条相同）⇒ **两个机型独立复现**了否定结论。

**全块差分**（`tools/blockdiff.py`）：

| 对照 | 块 0 | 块 1 | 块 2 | 块 3 | 块 4 |
|---|---|---|---|---|---|
| E-M5 v2.2→v2.3 | 3,319,143 B 变 | **0** | **0** | **0** | **0** |
| E-PM2 v1.5→v1.6 | 2,969,352 B 变 | **0** | **0** | **0** | **0** |

⇒ **修复完全落在块 0**；块 1（多语言+字体）、块 2（6-bit 编码区）、块 3（叠加位图）一个字节未动。

**版本间字符串增减**（`tools/str_delta.py`）：只在修复后出现的 210 条、只在修复前出现的 206 条
字符串中，**有意义的标识符为 0** ⇒ 修复未引入任何新命名符号，是纯粹的既有代码行为改动。

**语义差分基建**：块 0 导入 Ghidra → 全量反汇编建函数 → 导出归一化反汇编
（`tools/ghidra/Mn103DumpNormalized2.java`，分支目标→`T`、镜像内地址→`A`、
**RAM 全局与 mask ROM 地址原样保留**）。E-M5 两版各 54,8xx 个函数，
其中 **45,067 个函数指纹完全相同**（82.1%）——构成稳定基座，
改动最少的配对即补丁候选（`tools/semdiff2.py`）。

---

### 5.9 第十五轮：指令级差分 ⇒ 修复实体不在 `.BIN` 代码里（2026-10-23 新增）

> 完整证据：[`evidence/af_fix_2018/af_fix_instr_level_negative_result.md`](../evidence/af_fix_2018/af_fix_instr_level_negative_result.md)

**方法**。以「镜头 ID 两字节前缀比较链」为锚点——该链在 E-PM2 / E-M5 的
修复前与修复后版本里**地址完全不动**
（E-PM2 `0x403D3D1E`、E-M5 `0x904B26CC`），
因此该段代码的**指令边界天然对齐**，可以做逐条指令比对（`tools/instr_diff.py`，
GNU objdump `--target=mn10300-elf --insn-width=16`）。

**观察**：

| 机型对 | 对齐窗口 | 指令数 | 插入/删除 | 操作数差异构成 |
|---|---|---|---|---|
| E-PM2 v1.5.0.1 → v1.6.0.0 | `0x40300000..0x40480000`（1.5 MB） | 645,858 | **0 / 0** | 7,608 × `+0x2AC`（mask ROM 位移）＋ 529 × 0（链接噪声） |
| E-M5 v2.2 → v2.3 | `0x90460000..0x904E8000`（576 KB） | 217,190 | **0 / 0** | 4,363 × `+0x2C0`（mask ROM 位移）＋ 1,469 × 0 |

链函数本身 4 KB 窗口内，E-PM2 修复前后**只差 2 字节**、E-M5 只差 4 字节，
且差异就是 `fc dc <imm32>` 这条 **mask ROM 指针**：

```
E-PM2  0x403D3DD4   修复前 fc dc fc 1b 74 7e  (0x7E741BFC)  →  修复后 fc dc a8 1e 74 7e  (0x7E741EA8)
E-M5   0x904B2784   修复前 fc dc a6 66 87 7e  (0x7E8766A6)  →  修复后 fc dc 68 69 87 7e  (0x7E876968)
E-P5   0x403B7A0B   修复后 fc dc 8c 01 43 7e  (0x7E43018C)
```

**全块位移统计**（`tools/rom_ptr_diff.py`，扫描所有 `0x7D–0x7F` 区间的 32 位常量）：

| 机型对 | 主位移 | 次位移 |
|---|---|---|
| E-PM2 | `+0x2AC` × 11,362 | `+0x288` × 7,345 |
| E-M5 | `+0x2C0` × 12,285 | `+0x298` × 8,125 |

⇒ **机身 mask ROM 映像在修复版里被扩充了**（两个区段分别后移）。

**结论（观察级）**：2018-12-18 松下镜头 AF 修复的**实体内容不在固件 `.BIN` 的代码块里**，
而在机身 mask ROM 映像中；`.BIN` 里的代码只因引用偏移变化而被重新链接。

**对 §5.2 结论的修正**：原写「每镜头 AF 调校参数在机身 mask ROM ⇒ **固件补丁无法改写**」。
更准确的说法是「**在 `.BIN` 层面无法改写**（`.BIN` 的 4~5 个块运行时地址都不覆盖
`0x7Exxxxxx`）；但 **ROM 映像本身在官方修复版里被改写过**」。

**E-P5 1.8 坐标**：链函数内的 ROM 指针在 **`0x403B7A0B`**（值 `0x7E43018C`）；
白名单开关字 `0x605339A0` 仍在 `0x403B7A27` 被 `btst 4` 检查；
LENS_INFO 主表 `0x405E8EE0`（106 条）与 6 张 mask ROM 指针表
（`0x405EE4DC` 20 项 / `0x405EE828` 100 项 / `0x405EEAB4` 34 项 /
`0x405EEE6C` 46 项 / `0x405EEF58` 24 项 / `0x405EF0B4` 25 项）
**修复前后逐项相同**。

**覆盖边界（诚实声明）**：指令级对齐只在「地址不动」的窗口内成立。
把同一套差分跑满 E-PM2 整个块 0（14,155,712 B）时，
A/B 指令数 7,207,257 / 7,207,517，且有 790,644 / 790,904 处只剩单侧
⇒ 全块范围内线性反汇编边界会漂移。
因此本节结论**严格限定**在上述两个对齐窗口内，不外推到全块。

## 6. 固件内部功能解剖（块 0 解混淆后）

| 子系统 | 证据 |
|---|---|
| **自研 RTOS「USF」** | `USF debugging shell Version 1.10`；RTOS 调度统计 `id Name CPU CLASS pri bpri sts wait wobj timeout_ act wup sus` |
| **固件升级状态机** | `FIRMUP_CLI` / `FIRMUP_SRV` / `FIRMUP_CLI_POST` / `FIRMUP_FILE_POST` / `BC_FIRMUP` / `SCPU_FIRMUP` / `FIRMUP_LED`；`[firmup]REBOOT SYSTEM UPDATE.` / `[firmup]REBOOT USER UPDATE.` / `[firmup]...Binary file Hakken !!!!!`；`Execute_FirmwareUpdate info->display.id/size/success.id/success.size` |
| **完整 FAT12/16/32 驱动** | `SectorCluster` `bytesSector` `SC_sht` `SC_mask` `FATnum` `RootEntry` `RootLen` `FATbit` `FSInfo_LBA` `BkBoot_LBA` `RootCls` `TotalSectors` `FATSize` `ClusterMax` `BytesCluster` `BC_sht` `BC_mask` `Boot_LBA` `FAT_LBA` `ROOT_LBA` `DATA_LBA` `fat_end_mark` `WriteProtect` `FAT_Cleaned` `card_type` `ActiveFAT` `Hidden_area` `Hidden_size` |
| **SD 卡升级路径** | `update fat` / `FAT_UPDATE` / `update_file_cash` / `TESTFILE.BIN` / `filetest:: update %04d/%02d/%02d %02d:%02d:%02d` / `create_entry_file` / `update_path_link_info` |
| **版本三元组** | `firm_version(BCD)` / `major_version` / `minor_version` / `hw_version` / `g_firmup_version` / `g_firmup_hw_version` / `API_VERSION_ROM_NUMBER` / `GEN REV=01.00` |
| **多核 IPC** | `IMG_CPU0_PRIVATE2LOCAL` / `IMG_CPU0_LOCAL2PRIVATE` |
| **身份字符串** | `OLYMPUS DIGITAL CAMERA` / `OLYMPUS IMAGING CORP.` / `E-P5` / `Copyright (c) 2004-2005 OLYMPUS IMAGING CO.,LTD.` |

> **对既有文档的更正**：`固件本体说明.md` 写"E-P5 官方流程是 USB 更新器 / SD 卡直刷仅部分机型支持"。
> 固件代码层面确实存在完整的"读卡 → 校验固件文件 → 写入 → FAT 清理"路径。
> 但**是否在机身菜单暴露该入口仍需实机验证**——本次为纯离线静态分析，未接触机身。

---

## 7. 官方更新器链路（PC 侧）

```
Olympus_E-P5_Firmware_1.8_Updater_Win64.exe   (PE32 i386, Olympus Corporation)
└─ .rsrc CAB
   ├─ setup.ini              VERSION="2.00" / VERSIONNUM="2000"
   ├─ FwUpTool.msi           (含 Binary.OlyInstallLib.dll)
   ├─ cab/FwUpTool.cab → application.cab
   │  ├─ CameraUpdate.exe    546,792 B  PE32 i386
   │  │   PDB: x:\VSS_data\FwUpTool\FwUpTool\common\bin\Release\CameraUpdate.pdb
   │  ├─ OlylwApi2.dll       27 个 Oly* 导出（注册表/磁盘/设备查询/文件复制），依赖 SETUPAPI.dll
   │  ├─ OlyGin.dll          CreateInst / DeleteInst，依赖 SETUPAPI.dll
   │  ├─ OlyWebPAC.dll       CreatePACforVInstance，依赖 WINHTTP.dll（HTTPS 取固件）
   │  ├─ OlyWebXMLMgr.dll    CreateXMLManager
   │  ├─ OlyWebAccess.dll    CreateWebAccessInstance
   │  ├─ OlyGross.dll        OlyGetString / OlyGlossInit / OlyGlossExit（346 条 UTF-16 "firmware" 文案）
   │  └─ OlyBar.dll, OlyUICtl2.dll, olycms.dll, olysurf.bin, skin/
   └─ Data/ OlyCCDriverInstaller_x64/x86.EXE, vcredist_*, msxml.msi
```

**向导状态机**（MFC 类名直接给出）：
`CFwUpLauncherPane → CFwUpLicencePane → CFwUpSelectPane → CFwUpAddLangPane → CFwUpStartPane → CFwUpDuringUpdatePane → CFwUpRestoreMysetPane → CFwUpFinishPane`
与固件侧 `FIRMUP_FILE_POST` / `[firmup]REBOOT USER UPDATE.` / `RestoreMyset` 语义吻合。

**关键结论**：在 `CameraUpdate.exe` 与全部 `Oly*.dll` 中搜索 `OE\x10\x80` **0 命中**
→ **PC 端把 `.BIN` 当不透明字节流传输；OE 容器的解析、混淆还原、块校验全部由机身 bootloader 完成。**

---

## 8. Binwalk / Unblob 结果（阴性结论 + 误报说明）

### Binwalk 3.1.0（REA Evidence `ev_52af9046…`）
检出 3 个区域，**全部为误报**：

| 偏移 | 签名 | 误报依据 |
|---|---|---|
| `0x000CEE03` | `srecord_generic` (19,448,074 B) | 区域可打印率仅 27.7%，全区域仅 77 个 S-record 记号 → 巧合匹配 |
| `0x029E1153` | `zlib` (97 B) | 解压报 `invalid distance too far back` |
| `0x02A06807` | `zlib` (115 B) | 同上 |

同时确认固件中**不存在任何标准容器**：gzip / xz / bzip2 / lz4 / zstd / squashfs / UBI / cramfs / ext4 / ZIP / ELF 全部 0 命中（ELF 0 命中是因为块 0 代码被混淆打包）。

### Unblob 26.6.4（REA Evidence `ev_581bd71d…`）
**0 文件、0 chunk**，coverage 完整 → 固件不含任何可被标准工具识别的容器。

---

## 9. 未解问题（诚实边界）

| 项 | 状态 | 阻塞原因 |
|---|---|---|
| **1.8 AF 修复的补丁字节** | **原假设已证伪，落点收窄到块 0 代码** | E-M5 v2.2→v2.3 与 E-PM2 v1.5→v1.6 **双机型独立复现**：镜头 ID 前缀比较链与 LENS_INFO 镜头主表两版**完全相同**。全块差分证明**块 1/2/3 逐字节相同**，修复只可能在块 0（§5.6、§5.8）。字节级差分不可用（整包重编译，23% 字节变化），已改用字符串锚点对齐 + Ghidra 归一化函数语义差分（45,067/54,843 函数指纹相同） |
| **艺术滤镜效果注册表**（效果 ID → 处理函数/参数块） | 未解 | `art_*` 名字是**残留符号名表**，Ghidra 全量验证 6,488,149 条指令中 0 条引用（详见 `evidence/art_filter/art_filter_analysis.md`）。Ghidra 侧已锁定 3 个候选分派函数 `FUN_4047975c`/`FUN_4048b6d2`/`FUN_4049893c`，尚未证明哪个是 art 效果表 |
| **滤镜增益表 / 参数表位置** | 未解 | 块 0 纯数据 / 块 2 六位加密区 / 机身 mask ROM 三选一未定 |
| **录像艺术滤镜解锁的确切字节** | 未解 | 门控函数 `art_chk_type_mov` 的地址尚未确定（`art_chk_type_rec`/`_mov` 成对存在已确认） |
| **H-ES200 / H-ES50200 的 4 字节镜头 ID** | 未解 | 固件内无镜头型号名字符串；镜头 ID 由镜头经 I²C 应答，型号↔ID 对应表在 mask ROM 或在镜头内部。**公开世界亦不存在该对照表**（已全量检索 GitHub / grep.app / Sourcegraph / DuckDuckGo / archive.org） |
| **块 2 的 6-bit 编码算法** | 未解 | **四个独立项目（E-PL3、E-M1 III、fishcu、oly_fw_tools）均未解开**；已确定它是跨代共享资产 |
| ROM 描述符表 `0x7E5558E8` | 不在镜像内 | 位于机身 mask ROM，需 dump 实机或 boot ROM |
| E-P5 SoC 全貌 | 部分 | 本文件只含 1 个 MN103 核的代码；`IMG_CPU0_*` 暗示多核，其他核不在本镜像 |
| `kind`/`flags` 之外的官方字段表 | 部分 | `OlympusFwConstants.hxx` 只给出 flags 枚举，未给 `loadingAddress` 语义 |

---

## 10. 交付物

```
E-P5_固件_1.8/rea_work/
├── report/逆向分析报告_E-P5_Ver1.8.md      ← 本报告
├── decoded/                                   ← 混淆还原后的 4 个块
│   ├── 00_0100_402c0020.decoded.bin   15 MiB  主控代码（MN103）
│   ├── 01_0101_427c0020.decoded.bin   21.9 MiB 语言/字体
│   ├── 02_0106_43da0020.decoded.bin   2.4 MiB  6-bit 区
│   ├── 03_0104_44000020.decoded.bin   3.5 MiB  叠加位图
│   ├── manifest.json                      容器元数据 + 往返校验
│   ├── strings.jsonl / leads.jsonl        全部字符串 / 重点子集
├── disasm/                                  ← 反汇编样本
│   ├── entry_0x402C0000.txt                块0 入口/启动代码
│   ├── memmap_table_0x402F8800.txt        内存映射描述符表
│   ├── lens_info_dump_0x405BDF00.txt      LENS_INFO 字段打印函数
│   └── lens_state_switch.txt              镜头状态机
├── toolchain/mn10300-objdump              自建 binutils 2.45 (mn10300-elf)
├── evidence/                               ← REA 原始 Evidence ×3
└── scripts/                               ← 可复现脚本 + Olympus 官方源码
```

### 引用来源
- REA 6.4.0 本地分析（Binwalk 3.1.0 / Unblob 26.6.4），Evidence ID 见 §8
- Olympus 官方 `oly_fw_tools` 源码（MIT 家族，`BlockHeadTail` / `Scramble` / `Checksum` / `Constants`）
- `fishcu/oly_fw_analysis`（容器实现，注明源自 Altsoph / mx3，CHDK thread 2471）
- `cmdada/em10-fw`（GPL-3.0）— MN103 模拟器、SLEIGH 规范、ISA 手册
- `sympho-ru/olympus-e-pl3-research`（Apache-2.0）— 同容器谱系、已验证指令语料、逐段 SHA-256
- `nivag8899/olympus-em1m3-research` — 跨代 6-bit 块结论
- 官方固件说明页 `https://dl01.om-digitalsolutions.net/ww/ud2/ENU/0001/1080/index08a.html`
- 官方固件总表 `https://support.jp.omsystem.com/en/support/imsg/digicamera/download/software/firm/e1/`
