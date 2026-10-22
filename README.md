# ep5-fw-reverse — 奥林巴斯 PEN E-P5 固件 (Ver. 1.8) 逆向分析

对官方 E-P5 机身固件 `OLY_E_108_1800_0000_0000.BIN` 的离线静态逆向成果。

**容器格式已 100% 破解并逐字节验证**；指令集确认为 **Panasonic MN1030/MN103S**；已建立可用的 MN103 反汇编管线，
并还原出机身内存映射、镜头信息结构体布局与固件升级状态机。

> **本仓库不含固件本体**（版权原因）。所有内容均可由官方镜像重新生成，见 [`reproduce.sh`](reproduce.sh)。

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
evidence/  REA 6.4.0 原始 Evidence JSON（Binwalk 扫描 / Unblob 提取 / PE 资源）
           + af_fix_2018/：1.8 松下镜头 AF 修复的跨机型对照数据
scripts/   可复现分析脚本 + Olympus 官方 oly_fw_tools 源码（格式权威定义）
tools/     第三方参考实现（fishcu/oly_fw_analysis 的容器解析器）+ 工具链构建脚本
reproduce.sh              一键复现：校验 → 解混淆 → 反汇编
PROVENANCE.md             逐项来源、许可与再分发边界
工作日志.md                逐日工作日志（结论、证据、阻塞与下一步）
固件本体说明.md            固件获取与校验说明
```

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
固件本体需自行准备（见 [`PROVENANCE.md`](PROVENANCE.md) §2）。

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

## 已知未解问题

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

- 本仓库为**个人研究归档**，私有仓库。
- 奥林巴斯/OM SYSTEM 固件本体与更新器二进制**均未包含**（版权）。
- `scripts/OlympusFw*.hxx` 与 `scripts/EstimateLoadAddress.hxx` 来自 `cmdada/em10-fw` 内 vendor 的
  Olympus 官方工具 `oly_fw_tools`（用于说明格式定义）。
- `tools/oly_container.py` 来自 `fishcu/oly_fw_analysis`，其实现注明源自 Altsoph / mx3
  （CHDK thread 2471）。
