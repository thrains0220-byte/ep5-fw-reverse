# 第二十三轮：官方通道穷尽关闭 + mask ROM dump 流水线（把卡点变成一条命令）

> 日期：2026-10-24
> 性质：可复现的否定性结论 + 可执行工具
> 相关：[`round22_maskrom_requirements_and_lensid.md`](round22_maskrom_requirements_and_lensid.md)（清单 R1–R12）、
> [`community_patch_A_semantics.md`](community_patch_A_semantics.md)

---

## 0. 本轮结论

> **固件（`.BIN`）这条线已经走到尽头**：官方接口在 41 组请求字段变体下**只返回 1 个 `.BIN`**，
> 更新器本体也已从 CDN 下架。**机身 mask ROM 无法由软件获得。**
>
> ⇒ 剩下的判据问题**只剩一个入口：实机 dump**。
> ⇒ 本轮把这个入口做成了**一条命令**：`tools/rom_fill_report.py`。

---

## 1. 通道 B（OMSRV / `fcache.do`）—— **穷尽关闭**

### 1.1 背景：2025-12 起 OM 改了下载方式

直链 `.BIN` 现在不再可直接下载，必须先向
`https://fw01.om-digitalsolutions.net/ww_inform/fcache.do` 提交 XML，
换取带 `Expires` / `Signature` 的 URL（CloudFront 签名）。
这意味着**所有官方固件分发都经过这一个接口** —— 是查 ROM 的最后机会。

### 1.2 第二十轮漏掉了什么

第二十轮的 `tools/omsrv_multifile.py` 只变了 `firmup_mode`（0–3）与端点，
**其余字段全部固定**：

```
application=FWUT   type=0000   version=00005000   os=WIN   country_code=0001
```

而更新器 `OlympusUpdater.exe`（约 15.7 MB）本身也要下载，**很可能由同一服务按这些字段区分下发**。

### 1.3 本轮的系统性探测（新工具 `tools/omsrv_toolprobe.py`）

对 E-P5（`hard_code = OLYE108000000000`）**逐一变化 8 个非机型字段**，共 **41 组**：

| 变化的字段 | 取值 |
|---|---|
| `application` | FWUT / FWUD / DCU / DCUD / OLYMPUS / APP / （空） |
| `type` | 0000 / 0001 / 0002 / 0003 / 0100 |
| `version` | 00005000 / 00010000 / 00020000 / 00003000 / 00000000 / 00001000 / 00005100 |
| `os` | WIN / MAC / OSX / LIN |
| `country_code` | 0001 / 0002 / 0000 / 0091 |
| `language` | ENU / JPN / CHS |
| `firmup_mode` | 0 / 1 / 2 / 3 / 4 |
| `firmware_version` | 00001000 / 00001800 / 00002000 / 00000000 |
| 组合 | application+type / application+version / os+application / type+version |

### 1.4 结果

【观察】**41 组里 40 组返回且仅返回 1 个文件**：

```
file_name = OLY_E_108_1800_0000_0000.BIN
file_size = 44,826,624
up_date   = 2018/12/18
model_name= E-P5
```

- `application=`（空）→ 报错 `error_code=20 / There are no items. //firmware_demand/application`
  ⇒ 服务端**确实校验**这些字段，但**不因它们改变而多返回文件**。
- `firmware_version=00001800` / `00002000` → `<file_name>` 为空
  ⇒ 请求一个"比现装版本更新"的版本时，服务端说"没有"，即**只发最新版**。
- 附带发现：`language=CHS` 时签名 URL 的主机变成 **`cameras.om-digitalsolutions.cn`**（中国镜像）。

【结论】**通道 B 彻底关闭。** 官方接口对 E-P5 **只发一个 `.BIN`**，无论怎么变字段。

---

## 2. 通道 D（官方更新器资源）—— **也关闭**

【观察】`Olympus_E-P5_Firmware_1.8_Updater_Win64.exe` 的直链已 404。探测 7 组候选路径全部 404：

| 候选 URL | 结果 |
|---|---|
| `/OMDS/UPDATERS/0001/1080/OlympusUpdater.exe` | 404 |
| `/OMDS/UPDATERS/OlympusUpdater.exe` | 404 |
| `/OMDS/FIRMWARES/0001/1080/OlympusUpdater.exe` | 404 |
| `/OMDS/FIRMWARES/0001/1080/OLY_E_108_1800_0000_0000.exe` | 404 |
| `cameras.om-digitalsolutions.cn/OMDS/FIRMWARES/0001/1080/OlympusUpdater.exe` | 404 |
| `/ww/ud2/ENU/0001/1080/OlympusUpdater.exe` | 404 |
| `/ww/ud2/ENU/0001/1080/E-P5_1800_Updater_Win64.exe` 等 6 个名字 | 404 |

【观察】Wayback CDX 全量存档（21,038 条 URL，含 `dl01` / `olympus.com` /
`olympus-imaging.com` / `omsystem.com` 全部主机）中**没有任何 E-P5 更新器**，
只有 2000 年代的老文件。

【观察】即使拿到（第十七轮已拿到并解包过）：`.rsrc` 里唯一的巨型资源是
15,996,237 B 的 MSCF，解出的是 **2016 年通用安装包**
（`setup_FWT.exe` / `FwUpTool.msi` / `OlyGlossaries.dll` / 驱动 / vcredist），
**无 ROM、无第二份固件**；`CameraUpdate.exe` 本体仅 546,792 B，
22 个 PE 资源全是图标与对话框（已用 `inspect_pe_resources` 全量枚举）。

【结论】**通道 D 关闭。**

---

## 3. 一个逻辑上的**决定性推论**

【推断，高置信】**若机身 mask ROM 是可升级的，它必然出现在 `.BIN` 里。**

- 官方唯一的固件交付物就是 `.BIN`（§1、§2 已穷尽）；
- 50 个固件映像 / 245 个块 / 59 个不同装载地址中，**0 个落在 `0x7Exxxxxx`**；
- 块 0 内部最长「有意义」匹配段仅 255,778 B，远小于 ROM 密集区 ≈ 13.4 MB。

⇒ **`.BIN` 里没有 ROM ⇒ ROM 不是通过固件更新写入的 ⇒ 它是出厂烧录的（masked）**。
⇒ **任何软件渠道都不可能拿到它。**
⇒ **只剩两条路：实机 dump（芯片读出），或放弃「读 ROM」这条路，改走 ROM 侧的替代方案。**

---

## 4. ★ 把卡点变成一条命令：`tools/rom_fill_report.py`

### 4.1 它做什么

读入一份 mask ROM 镜像（裸二进制，默认基址 `0x7E000000`，覆盖 `0x7E000000–0x7EFFFFFF`），
按第 22 轮的清单 **R1–R12** 逐条读出并解释：

| 条目 | 读什么 | 怎么解释 |
|---|---|---|
| **R1 / R2** | `0x7E452BDC` / `0x7E452BE4` 各 4 字节 | 两种解释并列：{u16 首ID, u16 项数} 与 {u32 打包值}；同时标注它在 R3 族里的序号 |
| **R3** | `0x7E452B30` 起 52 项 × 4 B | 全部列出（每项两种解释） |
| **R4 / R5 / R6** | `0x7E5C9809` / `0x7E5C9B1C` / `0x7E5C9D1E` / `0x7E5C9E0E` | hexdump 预览 |
| **R7** | 10 个效果参数块 | 每块前 64 字节 u16 |
| **R8** | `0x7E897CF4` 16 槽 × 8 B | 逐槽打印 `{u32 子ID, u32 handler}` |
| **R9 / R10** | `0x7E8973D0` / `0x7E503C78` + 3 个错误串 + 2 个输出表 | hexdump / 字符串 |
| **R11 / R12** | `0x7E429774` / `0x7E429540` 各 6 项 `{u32 ID, u32 ptr}` | **跟随指针**把参数数组读出来 |
| 全部 | — | 同时输出 dump 的 SHA-256 与覆盖范围 |

### 4.2 自测

【观察】用一份 **16 MB 合成 ROM**（在 R1 写 `"A03F"+{10,0}`、R2 写 `"A042"+{4,0}`、
R3 族 52 项、R8 16 槽、R11 6 项带指针）跑通，输出正确：

```
R1(照片) @ 0x7E452BDC  [= R3 族第 43 项]
  A:{首ID=0x3041(0A) 项数=17971}   B:0x46333041
  0000  41 30 33 46                 A03F
R2(录像) @ 0x7E452BE4  [= R3 族第 45 项]
  0000  41 30 34 32                 A042
R11 @ 0x7E429774
  项 0  0x7E429774  ID=0x0000A100  ptr=0x7E430000
      参数数组前 32 字节: 00 00 01 00 02 00 ...
```

【附带发现】**R1 / R2 就是那 52 项描述符族的第 43 / 45 项**
（`(addr − 0x7E452B30) / 4`）—— 这一点在第十七轮「52 项 4 字节步长」时就已隐含，
本轮由自测数据的覆盖关系显式暴露。

### 4.3 用法

```powershell
# 拿到 dump 后，一条命令
python tools/rom_fill_report.py --rom maskrom.bin --rom-base 0x7E000000
python tools/rom_fill_report.py --rom maskrom.bin --json report.json
python tools/rom_fill_report.py --rom maskrom.bin --only R1 R2      # 只看最关键的两条
```

### 4.4 dump 需求

| 项 | 值 |
|---|---|
| 需要的范围 | `0x7E000000 – 0x7EFFFFFF`（**16 MB**） |
| 已知被引用的最高地址 | `0x7EEF04E9`（本轮 R11 邻近）/ `0x7E897CF4`（R8） |
| 已知被引用的最低地址 | `0x7E429540`（R12）/ `0x7E452B30`（R3） |
| 内容 | 机身 masked ROM 原样 dump（**不做任何解密/反混淆**） |
| 校验 | 工具会打印 dump 的 SHA-256 与实际覆盖范围，超范围会显式标注「超出 dump 范围」 |

---

## 5. 收官判据表：哪些已经闭合，哪些只剩硬件

| 问题 | 状态 | 证据 |
|---|---|---|
| 容器格式 | ✅ **完全破解** | 往返逐字节一致 |
| 艺术子系统的**结构**（菜单→效果ID→20槽→ROM 参数块） | ✅ **完全破解** | `evidence/art_filter/` |
| 菜单 10 项 ↔ 10 个效果实现 ↔ 20 槽 | ✅ **完全破解** | 第十二轮 |
| 社区补丁的两处改动**语义** | ✅ **完全破解** | 第二十一轮 |
| E-P5 的 AF 步数上限落点 + 配方 | ✅ **定位 + 配方已校验** | 第二十一/二十二轮 |
| 镜头 ID 白名单在 E-P5 的有无 | ✅ **已判定：没有** | 第二十二轮（8 路径穷尽） |
| 「照片 10 / 录像 4」的**内容** | ⛔ **只在 mask ROM** | R1/R2 |
| 新增滤镜**算法** | ⛔ **只在 mask ROM，且不可升级** | §3 |
| 官方下发通道 B/D | ⛔ **已穷尽关闭** | §1、§2 |
| AF 上限彻底放开（量程公式） | 🔜 **需实机** | 待办 |

---

## 6. 本轮新增工具

| 工具 | 作用 |
|---|---|
| `tools/omsrv_toolprobe.py` | 系统性变化 `fcache.do` 请求的 8 个非机型字段（41 组），检查是否返回**多于一个**文件或非 `.BIN` |
| `tools/rom_fill_report.py` | **mask ROM dump 到位后的一条命令**：读出 R1–R12 全部判据并解释；自带合成 ROM 自测 |

## 7. 复现命令

```powershell
# 通道 B 穷尽探测（41 组，约 3 分钟）
python tools/omsrv_toolprobe.py --out fw-work/omsrv_toolprobe.json

# ROM 流水线自测
python tools/rom_fill_report.py --rom fw-work/fake_maskrom.bin --rom-base 0x7E000000 --only R1 R2 R11
```
