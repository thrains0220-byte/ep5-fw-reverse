# `firmware/` —— 固件资料包

本目录收录本项目逆向分析所用的**全部原始固件、社区改机归档与采集过程资料**。

> ## ⚠️ 版权与使用边界
>
> * 本目录内的 `.BIN` / `.zip` / `.rar` 均为 **Olympus（横滨奥林巴斯 / Taiyo Yuden）**
>   的专有固件与更新产物，**著作权属于原厂**，本项目**不主张任何权利**。
> * 这些文件取自 **xdel.ru**（泰语镜像站）与 **Wayback Machine** 上的奥林巴斯官方镜像。
> * 文件仅供**本项目的逆向研究、备份与互操作分析**使用；
>   **不得**用于商业目的，**不得**再分发，**不得**用于生成可分发的改机固件。
> * 压缩件（`*.BIN.lzma`）是 **LZMA 无损**压缩，与原 `.BIN` **逐字节等价**；
>   `MANIFEST.sha256` 的 ORIG 段记录了每个原始 `.BIN` 的 SHA-256，
>   可随时解压还原并校验（见 §4）。
> * **社区改机归档**（`community/`）是第三方社区产物，同样受原厂著作权约束，
>   本项目仅作**补丁字节分析**用途。

---

## 1. 目录结构

```
firmware/
  README.md              本文件
  MANIFEST.sha256        全部文件的 SHA-256（归档段 + 原始 .BIN 段）
  stock/<model>/*.BIN.lzma     66 个原版固件（LZMA 无损）
  pre_fix/*.BIN.lzma           17 个「修复前」基线固件（LZMA 无损）
  community/*.zip|*.rar        12 个社区改机归档（原样存放）
  notes/                       更新协议 / 服务器报文 / 站点索引等文本资料
```

| 目录 | 内容 | 数量 |
|---|---|---|
| `stock/` | 从 xdel.ru `original/` 取得的全部机型原版固件 | 66 |
| `pre_fix/` | xdel.ru `pre_fix/` 目录的早期版本（含 E-M5 v2.0–v2.3、E-PM2 v1.1–v1.6 等**AF 修复前基线**） | 17 |
| `community/` | xdel.ru `patched/` 与 `patched_yandex/` 的社区改机归档 | 12 |
| `notes/` | `olyhttp/`（奥林巴斯 HTTP 更新协议）、`omsrv/`（MSRV 服务器报文样例）、`orig_index/`（机型索引页）、`web/`（固件目录页与 `ofu_catalog.json`） | 59 |

### 机型目录名对照

`stock/` 下的目录名沿用 xdel.ru 的简写：

| 目录 | 机型 | 目录 | 机型 |
|---|---|---|---|
| `em1` | E-M1 | `em5` | E-M5 |
| `em10` | E-M10 | `em5mk2` | E-M5 II |
| `em10mk2` | E-M10 II | `em5mk3` | E-M5 III |
| `em10mk3` | E-M10 III | `em1mk2` | E-M1 II |
| `em10mk4` | E-M10 IV | `em1mk3` | E-M1 III |
| `em1x` | E-M1 X | `penf` | PEN-F |
| `penepl1`/`penepl1s` | E-PL1 / E-PL1s | `penepl3`…`penepl9` | E-PL3 … E-PL9 |

> `penepl5` 即 **E-P5 / E-PM2**（同一机身的两种市场命名）。

---

## 2. 固件文件名约定

`OLY_E_<model>_<version>_<build>_<x>_<x>.BIN`

| 字段 | 含义 | 例 |
|---|---|---|
| `E_<model>` | 机型代码（十进制） | `E_097` = E-M5，`E_101` = E-P5/E-PM2，`E_118` = E-M5 II，`E_139` = E-M1 III |
| `<version>` | 版本（4 位） | `2300` = v2.3，`1600` = v1.6 |
| 后 3 段 | 构建号/修订号 | `0000_0000` |

社区改机归档内则使用 `<model>9999.bin` 命名（`9999` 表示「非官方构建」）。

---

## 3. 容器格式（已完全破解）

Olympus `.BIN` 是**混淆块容器**，本项目已 100% 破解，往返逐字节一致：

| 项 | 内容 |
|---|---|
| 结构 | 4~6 个块，每块 = 32 B 头 + payload + 32 B 尾 |
| 混淆 | 16 字节内 16 列字节置换 + 全字节 XOR `0xFF` |
| 置换表 | `DECODE_ORDER = (1,3,0,2,6,4,7,5,11,10,9,8,13,14,12,15)` |
| 校验 | **加法 sum32**（`-Σ(u32 LE)`），不是 CRC |
| 工具 | `tools/oly_container.py`（`decode` / `encode` / `replace_payload`，自动重算尾校验和） |

块 0 = 主代码块（MN10300 指令 + 数据），块 1 = 多语言 UI 字符串池 + 字体，
块 2 = 6-bit 编码区（**未解**），块 3 = 文字叠加位图，块 4/5 = 杂项。

---

## 4. 校验与还原

```sh
# 全量校验（逐文件 SHA-256 + 逐个解压 .lzma 还原原始 .BIN 比对）
python tools/verify_firmware_bundle.py --deep

# 手工还原某个固件
python -c "import lzma,shutil,sys; \
  shutil.copyfileobj(lzma.open(sys.argv[1],'rb'), open(sys.argv[2],'wb'))" \
  firmware/stock/em5/OLY_E_097_2300_0000_0000.BIN.lzma out.BIN
```

`MANIFEST.sha256` 格式：

```
# --- ARCHIVE (仓库内实际文件) ---
<sha256>  <相对 firmware/ 的路径>
...
# --- ORIG (原始 .BIN 的哈希, 由 .BIN.lzma 无损还原) ---
<sha256>  <原始 .BIN 的路径>
...
```

---

## 5. 采集来源

| 来源 | 内容 | 备注 |
|---|---|---|
| **xdel.ru** `original/` | 66 个原版固件 | 泰语镜像，含历史版本 |
| **xdel.ru** `pre_fix/` | 17 个修复前基线 | AF 修复研究的唯一来源 |
| **xdel.ru** `patched/`、`patched_yandex/` | 12 个社区改机归档 | 唯一公开的「解锁」字节先例 |
| **Wayback** `dl01.om-digitalsolutions.net/OMDS/FIRMWARES/0001/<model>/` | 52 个 `.BIN` | **只存最新一版**（5 域名 / 21,038 URL 全量普查确认） |
| 官方直链 | — | 403（CloudFront 签名失效） |

Wayback 整文件 GET 会被限流成 4730 B 错误页，**必须用 Range 分块下载**
（见 `fw-work/get_one_win.sh`）。

---

## 6. 与本项目其余部分的关系

```
firmware/                 原始素材
   │ oly_container.py 解混淆
   ▼
decoded/                  解混淆后的块（E-P5 v1.8 为权威基线）
   │ Ghidra + MN10300 SLEIGH 模块
   ▼
evidence/  docs/  tools/  坐标、伪代码、结论、方法论
```

- **权威基线**：`decoded/00_0100_402c0020.decoded.bin`（E-P5 v1.8 块 0，15,728,576 B）
- **容器往返自检**：`decode → encode` 与源文件 SHA-256 完全相同
- **社区补丁验证**：E-M5 II v4.1 补丁偏移与 fishcu/oly_fw_analysis 的独立记录
  `0x3f2ad5 / 0x534866 / 0x53486c` **逐字节吻合**
