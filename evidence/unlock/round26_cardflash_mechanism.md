# 第二十六轮：★ E-P5 卡刷机制逆向（文件名规则 + 完整流程 + 可写分区清单）

> 日期：2026-10-24
> 性质：**静态观察**，全部来自 E-P5 v1.8 块 0 的字符串池与数据表
> 目的：搞清「相机到底在卡上找什么文件」，以及「固件更新能写哪些分区」

---

## 0. 结论

| 项 | 结论 |
|---|---|
| **卡刷文件名规则** | 固件里存的是**通配符模板**（`?` 是字面量，不是 printf）：`?108????BIN` + 12 个类型前缀 |
| **目录** | `DCOLYMP`（在 [firmup] 代码区里，与更新提示串相邻） |
| **更新流程** | mount → mount_ok → 找文件 → 读 file_size → DeSecramble → checksum → write_flash → REBOOT |
| **★ 可写分区** | **[firmup] 能写入 `ARTFIL`（艺术滤镜数据）、`BEAUTY`（美容）、`PIC`、`WAV`、`FRAME`、`ADJSLF`、`NOREXE`、`C3D`、`GUIDE`、`GPS`、`PSES`、`LANG`、`LENS`、`FLASH`、`OSD`、`USR`** |
| **⇒ 对「加滤镜」的意义** | **艺术滤镜数据是一个独立的可写分区（ARTFIL），不是只有 mask ROM 一条路** —— 这条路不依赖 ROM dump |

---

## 1. 文件名模板表（运行地址 `0x405F1EC4`）

固件里是一张 **12 字节定长**的字符串数组（每项 11 字符 + NUL）：

| 偏移 | 模板 | 推测类型 | 对应 [firmup] TYPE_ 常量 |
|---|---|---|---|
| `0x405F1EC4` | `S108????BIN` | **System（系统固件）** | `TYPE_FIRMUP_SYS` |
| `0x405F1ED0` | `E108????BIN` | Extension / 用户数据 | `TYPE_FIRMUP_SYS_IGAI` |
| `0x405F1EDC` | `G108????BIN` | GPS | `TYPE_GPS` |
| `0x405F1EE8` | `H108????BIN` | Hardware | — |
| `0x405F1EF4` | `W108????BIN` | Wireless / WAV | `TYPE_SOUND` |
| `0x405F1F00` | `A108????BIN` | Audio | `TYPE_SOUND` |
| `0x405F1F0C` | `M108????BIN` | Movie | `TYPE_C3D` |
| `0x405F1F18` | `V108????BIN` | Video | — |
| `0x405F1F24` | `D108????BIN` | Date | `TYPE_FIRMUP_DATE` |
| `0x405F1F30` | `T108????BIN` | — | `TYPE_STB` / `TYPE_FIRMUP_CHECK` |
| `0x405F1F3C` | `I108????BIN` | — | `TYPE_FIRMUP_USBUP` |
| `0x405F1F48` | `DATE????BIN` | 日期数据 | `TYPE_FIRMUP_DATE` |
| `0x405F1F54` | `PICTURE1JPG` | 样张 | `TYPE_PIC` |

【观察】`108` = E-P5 机型码（与容器头 `model_bytes = 1080` 一致）。
【观察】模板里是**字面的 `?`（0x3F）**，不是 `%` ⇒ 相机是**按通配模式扫描文件名**，不是格式化生成。
⇒ `????` = 4 个任意字符（版本号的各种写法）。

### 1.1 我们之前为什么全试错

| 我们试的 | 问题 |
|---|---|
| `DCOLYMP\E1089999.BIN` | **前缀是 `E`（扩展/用户数据），系统固件应该是 `S`** |
| 同上 | **带点号**，但模板 `?108????BIN` 的 `????` 只有 4 个字符 ⇒ 正确名字很可能是 `S1081800BIN`（无点） |
| 只试了 `DCOLYMP` 子目录 | 也可能是**卡根目录**（见 §2 的 `C:\WF*`） |

---

## 2. 卡根目录的另一套命名（运行地址 `0x40DF39B0`）

```
0x40DF39B0  'C:\WFDP0001.BIN'
0x40DF39C0  'C:\WFCL0101.BIN'
0x40DF39D0  'C:\WFCL0201.BIN'
0x40DF39D0  'C:\WFCL0%03d.BIN'      ← 唯一带 printf 的一个（按序号索引）
```

【观察】`C:` = 卡片根目录；`WF` = Write Firmware；`DP` / `CL` 为两类数据包；
`WFCL0%03d.BIN` 是**按序号生成**的文件名 ⇒ 相机对某类数据会扫一串编号。

---

## 3. [firmup] 完整流程（运行地址 `0x405F2090`–`0x405F2B45`）

```
[firmup]File Init Err.          文件初始化失败
[firmup]Mount Err:              挂载失败
[firmup]mount_ok                挂载成功
[firmup]ld_img_st               载入映像开始
[firmup]...Binary file Hakken !!!!!   ← 日文「発見」= 找到了二进制文件
[firmup]...read file_size =     读到文件大小
[firmup] Time                   计时
[firmup]Are?.                   版本比较
[firmup]SCPU Init Err.          子 CPU 初始化失败
[firmup]REBOOT SYSTEM UPDATE.   重启并应用系统更新
[firmup]REBOOT USER UPDATE.     重启并应用用户数据更新
[firmup]RebootFlag = 0x
DCOLYMP                         ← 目录名就在这一串里
[firmup]file_mount/             挂载流程
[firmup]DeSecramble             反混淆
[firmup]...checksum_error / ...FIRMUP_CHECKSUM_ERROR / write_flash_error
[firmup]TYPE_FIRMUP_SEARCH_ERROR
```

### 3.1 可写分区（`TYPE_FIRMUP_WRITE_*`）

```
USR      OSD      PIC      WAV      FRAME   ADJSLF   ★ARTFIL
NOREXE   C3D      GUIDE   ★BEAUTY  GPS     PSES     LANG
LENS     FLASH
```

【观察】每个分区还有对应的 `... Gets` 提示（`[firmup]...ARTFIL Gets` 等），
说明每类数据是**独立数据包**、可分别写入。

【观察】另有 `Maintenance::updateFirmwareCard` / `Maintenance::canUpdateFirmwareCard` /
`updateFirmware`（`0x40A85A37`/`0x40A85A53`/`0x40A85A73`）与
`api_firmup_Check_FirmwareUpdate` / `api_firmup_Execute_FirmwareUpdate`。

---

## 4. ★ 对「新增创意滤镜」路线的重大修正

【观察】`ARTFIL` 是**固件更新能写的分区**。

⇒ 之前的结论「艺术滤镜的一切都只在 mask ROM」**需要修正**：
**艺术滤镜数据（tone curve / 参数块 / 可能还有 LUT）有可能存在机身 flash 的独立
`ARTFIL` 分区里，而不是 mask ROM。**

【推断】如果 `ARTFIL` 分区可写且能被我们构造，那么：
- 「新增滤镜 / LUT 直出」**不需要 mask ROM dump**；
- 可以沿用 `[firmup]` 的包格式（`DeSecramble` + checksum）自己造一个 `ARTFIL` 包；
- 路线变成：**先解出 `ARTFIL` 分区的实际内容与包格式 → 构造新的艺术滤镜数据包 → 走卡刷/USB 更新写进去 → 再改块 0 让菜单露出它**。

【未知】`ARTFIL` 分区在机身 flash 的什么位置、包头格式、是否在 E-P5 上真的存在，
都需要实机确认（读 flash 分区表 / 用 `fileif` 把分区 dump 出来）。

---

## 5. 候选文件名（工具 `tools/make_cardflash_candidates.py` 已生成 12 个）

```
fw-work\SDCARD_CANDIDATES\
  01_S1081800BIN\S1081800BIN        ← 最可能：S=System，无点号，版本 1800
  02_S1089999BIN\S1089999BIN
  03_S108180_BIN\S108180.BIN
  04_S1089999_BIN\S1089999.BIN
  05_E1081800BIN\E1081800BIN
  06_E108180_BIN\E108180.BIN
  07_E1089999BIN\E1089999BIN
  08_E1089999_BIN\E1089999.BIN     ← 我们之前试的（错在前缀+点号）
  09_S1081800_BIN\S1081800.BIN
  10_WFDP0001_BIN\WFDP0001.BIN     ← 卡根目录命名
  11_WFCL0101_BIN\WFCL0101.BIN
  12_WFCL0201_BIN\WFCL0201.BIN
```

**每次只放一个**（多个候选同时放可能让相机报错而不是识别）。

---

## 6. 本轮方法学教训（重要）

【方法错误】第 20 轮「艺术滤镜字符串在块 0 内 0 引用 ⇒ 实现在 ROM」——**这个搜索方法无效**。
【观察】块 0 的字符串**不以绝对地址立即数出现**（连 `DCOLYMP`、`E108????BIN`、
`art_white_edge_pass_err` 之外的串都搜不到指针），而是通过
「基址 + 索引」的查表助手 + 字符串驻留表取用。
⇒ **跨机型/跨子系统的字符串定位必须用 Ghidra 的数据流引用分析，不能用字节搜索**。

【观察】6.49 M 条指令里，落在块 0 自身地址范围内的标量只有 **144 个不同值**，
且全是页对齐的 RAM 区基址 —— 印证了「字符串不按绝对地址引用」。

⇒ 待办：**破解字符串驻留表的 hash**（已定位唯一直接命中样本
`art_white_edge_pass_err` @ `0x405E5D68`，其后疑似跟一个 hash 值），
拿到它就有了全项目的「代码↔字符串」总钥匙。
