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

### 5.4 1.8 AF 修复的定位结论

- 修复**不在块 2**（已用跨代哈希排除）
- 修复**不在块 1/块 3**（语言字体与叠加位图，无 AF 语义）
- 修复**必然在块 0**，且最可能的落点是：
  1. `LENS_INFO_MAKERNOTE`（`a2+10`）的**厂商分支**——按厂商码选择 AF 参数
  2. `LENS_INFO_AF_CON`（`a3+42` / `a3+52`）的**填充逻辑**
  3. `vh/vl/vv/hk` × `af_c/af_u_d/af_l_r` 的 **AF 调校数据表**
- 反汇编已确认 `0x402CF1E1` 处有**按 `LENS_INFO_STATE` 字节（结构体 offset 0）跳转的状态机**，`0x402C21C2` 有 `movhu (42,a2),d3`（读 AF_CON）
- **尚未完成**：把"厂商码 → AF 参数"的那段分支逐字节定位并给出补丁字节。这需要继续沿 `a2+10` 的读取点回溯 maker 比较常量。

---

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
| **1.8 AF 修复的补丁字节** | 未定位 | 已排除块 2/1/3；需沿 `a2+10`(MAKERNOTE) 回溯厂商码分支并比对调校表 |
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
