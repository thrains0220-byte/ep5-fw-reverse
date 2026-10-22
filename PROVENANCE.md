# 来源与许可 / Provenance

本仓库为个人离线逆向研究的成果归档。逐项说明内容来源、许可与再分发边界。

---

## 1. 本仓库包含什么、不包含什么

### 包含

| 路径 | 内容 | 来源 |
|---|---|---|
| `report/` | 逆向分析报告 | 本次分析撰写 |
| `decoded/*.decoded.bin` | 由固件本体**反混淆**得到的 4 个块 | 派生于 Olympus 固件 |
| `decoded/manifest.json` | 容器元数据与校验结果 | 本次分析生成 |
| `decoded/strings.jsonl` / `leads.jsonl` | 字符串索引 | 本次分析生成 |
| `disasm/*.txt` | MN103 反汇编输出 | 本次分析生成 |
| `evidence/*.json` | REA 6.4.0 原始 Evidence | 本次分析生成 |
| `scripts/*.py` | 分析脚本 | 本次分析编写 |
| `scripts/OlympusFw*.hxx` | Olympus 官方 `oly_fw_tools` 源码 | **第三方（见 §3）** |
| `tools/oly_container.py` | 容器解析参考实现 | **第三方（见 §4）** |
| `固件本体说明.md` | 固件获取与校验说明 | 本次分析前的工作文档 |

### 不包含（有意排除）

| 内容 | 原因 |
|---|---|
| `OLY_E_108_1800_0000_0000.BIN` | Olympus 版权固件本体 |
| `Olympus_E-P5_Firmware_1.8_Updater_Win64.exe` / `.dmg` | Olympus 版权更新器 |
| `updater/` 解包出的 `CameraUpdate.exe`、`Oly*.dll`、`FwUpTool.msi` | 同上，均为 Olympus 版权二进制 |
| `toolchain/binutils/` | 自建工具链二进制（6.7 MB），由 `tools/build_mn103_objdump.sh` 复现 |

> **决策说明**：`decoded/*.decoded.bin` 是固件的**派生产物**，仍属衍生作品。本仓库设为私有、
> 仅供个人研究存档；如需公开分享，建议参照 `sympho-ru/olympus-e-pl3-research` 的
> "evidence-first" 做法——只发布固件坐标 / 长度 / SHA-256 / 反汇编指令文本，**不重新分发固件本体或派生字节**。
> 该项目的做法已记录在 `docs/` 规范中，可直接借鉴。

---

## 2. 目标固件来源

```
https://dl01.om-digitalsolutions.net/OMDS/FIRMWARES/0001/1080/OLY_E_108_1800_0000_0000.BIN
```

该 URL 现由 CloudFront 签名保护，直连返回 `403 MissingKey`；本次使用的副本取自
Internet Archive 对该官方 URL 的快照（timestamp `20250201203957`），SHA-1 与归档摘要一致。

校验值：

```
SHA-256  cc59a4e13b3bf6c46405bd396975cb9c93a7634b7a4a36822259b1fc498b5cfd
SHA-1    5J4T4SBWJXOL7F2T43SJUV34XESC3M53   (base32)
MD5      91c88791a8e3753ae22fcd464f33bf85
```

---

## 3. `scripts/OlympusFw*.hxx`、`scripts/EstimateLoadAddress.hxx`

来自 **`cmdada/em10-fw`**（GPL-3.0）内 vendor 的 Olympus 官方工具 **`oly_fw_tools`**：

```
em10-fw/tools/oly_fw_tools/oly_fw_tools/source/
    OlympusFwBlockHeadTail.hxx   ← 容器块头尾结构定义
    OlympusFwScramble.hxx        ← 混淆算法
    OlympusFwChecksum.hxx        ← 校验和算法
    OlympusFwConstants.hxx       ← BlockSig / Flags 枚举
    EstimateLoadAddress.hxx      ← 加载地址与字符串扫描辅助
```

保留这些文件是因为它们是**容器格式的权威定义**，使本仓库的结论从"逆向推断"升级为
"与厂商自家实现逐字段对齐"。Olympus 官方工具自身未声明明确的再分发许可，
此处仅作研究引用，**不随本仓库对外再分发**。

## 4. `tools/oly_container.py`

来自 **`fishcu/oly_fw_analysis`**。该文件的自述：

> Container/transform reference: Altsoph and mx3, CHDK thread 2471
> <https://chdk.setepontos.com/d/2471-olympus-emjustylus-series-fw-analysis>

该仓库未声明标准许可，另有 `RIGHTS-AND-PROVENANCE.md` 说明。**本仓库为私有，仅作个人研究引用。**

## 5. MN103 ISA 参考资料

| 资料 | 来源 |
|---|---|
| `MICROCOMPUTER MN1030/MN103S Instruction Manual` (Pub.No.13250-040E) | `cmdada/em10-fw/tools/olympus_cpu_isa_13250-040e.pdf`（松下 Matsushita 官方手册） |
| Ghidra SLEIGH 规范 `mn10300.igen` / `am33.igen` / `am33-2.igen` | `cmdada/em10-fw/emu/isa/`（取自 GDB `sim/mn10300`） |
| 53,425 条已验证 MN103 指令语料 | `sympho-ru/olympus-e-pl3-research`（Apache-2.0，文档 CC BY 4.0） |

## 6. E-PL3 同容器谱系比对

`decoded/02_0106_43da0020.decoded.bin` 与 `sympho-ru/olympus-e-pl3-research` 公开的
`evidence/ranges.jsonl` 逐段 SHA-256 比对结果：

| 区段（块内偏移 / 长度） | E-P5 | E-PL3 (Body 1.6) | 结果 |
|---|---|---|---|
| 0 / 8 | `5172fd5b…` | `fbfeb9ce…` | 不同（仅装载地址 `0x43DA0400` vs `0x43D00400`） |
| 8 / 984 | `8b147211…` | `8b147211…` | **完全相同** |
| 992 / 2,359,296 | `93c4e558…` | `93c4e558…` | **完全相同** |
| 2,360,288 / 130,016 | `255cf8d8…` | `255cf8d8…` | **完全相同** |

该结论用于排除"1.8 AF 修复位于块 2"这一假设。

## 7. 工具链

| 工具 | 版本 | 说明 |
|---|---|---|
| REA | 6.4.0 | 逆向分析框架（CLI）；`evidence/*.json` 为其原始输出 |
| GNU objdump | 2.45 | **自建**（`--target=mn10300-elf`），见 `tools/build_mn103_objdump.sh`；系统 binutils 2.38 无 mn10300 后端 |
| Binwalk | 3.1.0 | 自建（Rust），用于固件整体扫描 |
| Unblob | 26.6.4 | PyPI `unblob==26.6.4`，用于提取 `CameraUpdate.exe` 的 PE 资源 |
| Python | 3.13 | 分析脚本 |

---

## 8. 引用

- 官方固件版本说明：<https://dl01.om-digitalsolutions.net/ww/ud2/ENU/0001/1080/index08a.html>
- 官方固件总表：<https://support.jp.omsystem.com/en/support/imsg/digicamera/download/software/firm/e1/>
- CHDK thread 2471：<https://chdk.setepontos.com/d/2471-olympus-emjustylus-series-fw-analysis>
- `cmdada/em10-fw`：<https://github.com/cmdada/em10-fw>
- `fishcu/oly_fw_analysis`：<https://github.com/fishcu/oly_fw_analysis>
- `sympho-ru/olympus-e-pl3-research`：<https://github.com/sympho-ru/olympus-e-pl3-research>
- `nivag8899/olympus-em1m3-research`：<https://github.com/nivag8899/olympus-em1m3-research>
