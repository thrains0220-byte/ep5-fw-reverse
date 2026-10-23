# E-P5 实机操作手册（配合固件逆向）

> 目标机型：**Olympus PEN E-P5**
> 对应分析版本：**v1.8（2018-12-18）**
> 本手册只做三件事：**① 把相机对齐到 v1.8 ② 验证解锁补丁 ③ 取出机身 mask ROM**
>
> ⚠️ **风险声明**：卡刷固件有把相机刷成砖的可能（论坛上有先例）。
> 本手册每一步都给了**验收判据**和**回退方案**，请务必逐步验证，不要跳步。
> 本项目不提供任何绕过版权保护的机制；所有操作只用于你自有设备的研究用途。

---

## 0. 现状摘要

| 项 | 状态 |
|---|---|
| 容器格式 | ✅ 100% 破解，往返逐字节一致 |
| 「解锁」的两处社区补丁语义 | ✅ 完全解码（AF 步数上限 + 镜头 ID 白名单） |
| E-P5 上「解除 AF 步数上限」的补丁 | ✅ **已构建并校验**（6 字节，改动块 0 两处立即数） |
| 补丁工厂（按字节模式，不依赖偏移） | ✅ `tools/make_patched_firmware.py` |
| 机身 mask ROM 读取 | 🔄 相机固件内置 `memdump` 命令，入口待定位；改固件方案待做 |
| 「新增创意滤镜」 | ⛔ 取决于 mask ROM 是否运行时可写（`memload` 存在 ⇒ 待实测） |

**关键前提**：你手上的相机固件 **≤ v1.6**，而以上分析基于 **v1.8**。
官方服务**只提供最新版**（已实测：请求 `firmware_version=00001600` 仍只返回 v1.8），
所以**拿不到你当前版本的 `.BIN`** ⇒ **第 1 步就是先把相机升到 v1.8**。

---

## 1. 准备工作

| # | 事项 | 说明 |
|---|---|---|
| 1 | **SD 卡** | FAT32 格式、**≤32 GB**（老相机对 exFAT/64GB 支持不稳）。建议用一张小容量、卡上无重要数据的卡 |
| 2 | **读卡器** | 用来在 PC 与相机之间拷贝文件 |
| 3 | **电量** | 充满，或接电源适配器（DC-7）。**中途绝不能断电** |
| 4 | **官方 v1.8 固件** | 本仓库 `firmware/pre_fix/OLY_E_108_1800_0000_0000.BIN.lzma`（SHA-256 `cc59a4e13b3bf6c46405bd396975cb9c93a7634b7a4a36822259b1fc498b5cfd`） |
| 5 | **回退文件** | 保留一份未改动的官方 `.BIN`，万一 v1.8 起不来还能再试 |

解压官方固件：

```sh
python -c "import lzma;open('OLY_E_108_1800_0000_0000.BIN','wb').write(lzma.open(r'firmware/pre_fix/OLY_E_108_1800_0000_0000.BIN.lzma','rb').read())"
```

校验：

```sh
python -c "import hashlib;print(hashlib.sha256(open('OLY_E_108_1800_0000_0000.BIN','rb').read()).hexdigest())"
# 期望 cc59a4e13b3bf6c46405bd396975cb9c93a7634b7a4a36822259b1fc498b5cfd
```

---

## 2. 第 1 步 —— 卡刷官方 v1.8（把相机对齐到分析版本）

**为什么先做这一步**：① v1.8 含 2018-12-18 的松下 H-ES200/H-ES50200 AF 修复；
② 后续所有补丁都基于 v1.8 的块 0；③ 官方文件 + 官方流程，风险最低。

### 步骤

1. 在 SD 卡根目录建文件夹 **`DCOLYMP`**（全大写）。
2. 把 `OLY_E_108_1800_0000_0000.BIN` **改名**为 **`E1089999.BIN`**，放进 `DCOLYMP/`。
   （这个名字来自奥记官方固件总表，不是随意命名。）
3. 相机**关机**，插卡（**卡槽 1**，双卡机型用第一个槽）。
4. **按住 `OK` 键不放**，同时把电源拨到 `ON`。
5. 屏幕保持黑，前置**对焦辅助灯（AF assist lamp）**：
   - **常亮（橙）** = 相机已认出 `DCOLYMP/E1089999.BIN`，进入等待写入；
   - **快速闪烁** = 正在写入。**此时不要动相机、不要断电**，等它停。
6. 灯灭 / 相机自动关机后，把电源拨回 `OFF`，再拨到 `ON`。
7. 菜单 → `[设定]` → `[版本信息]`，确认显示 **1.8**。

### 验收判据
- `[版本信息]` 显示 `1.8` ⇒ 成功。
- AF 灯**没亮** ⇒ 相机没认出文件：检查卡是不是 FAT32、`DCOLYMP` 拼写、`E1089999.BIN` 文件名、
  文件是否在 `DCOLYMP/` 里而不是根目录。**这种情况不会刷砖，相机照常能用。**

### 回退方案
奥记**不检查降级**（官方论坛确认），所以刷成 v1.8 后仍可再刷别的版本。
但 v1.6 的 `.BIN` 本项目拿不到 ⇒ **实际上这是一条单向路**。
如果你不接受"先升到 1.8"，请告诉我，我会先想办法从你的相机里导出当前固件。

---

## 3. 第 2 步 —— 刷「解除 AF 驱动步数上限」补丁

### 这个补丁做了什么

社区改机补丁「模式 A」的第 1 处改动（12 字节）被本项目完全解码：

```
原函数（E-P5 v1.8: FUN_4058A207 @ 0x4058A207）
    step ∈ {6,3,8,9} → *cap = 0x6CC (1740 步)
    step == 4        → *cap = 0x1C20 (7200 步)
    实际生效 = min(cap, (0x800000 − thr)/(cnt+base))
```

本项目在 E-P5 上定位到同一机制（内联版），并给出**等长 6 字节**的等价改动：

| 位置 | 改动 |
|---|---|
| 块 0 `0x4058A31F` | `MOV 0x6cc,A3` → `MOV 0xffff,A3`（1740 → 65535） |
| 块 0 `0x4058A2DF` | `MOV 0x1c20,A3` → `MOV 0xffff,A3`（7200 → 65535） |

**诚实的效果边界**（脚本 `tools/af_cap_effect.py` 可复算）：
E-P5 多数分支真正的瓶颈是量程公式 `(0x800000 − thr)/(cnt+base)`，所以这 6 字节
**只对 `step == 3` 分支有实际增益**（1740 → 2363 / 2977，+36% / +71%），
其余分支不变。想彻底放开还要改 `0x800000`（`0x2CA256` / `0x2CA28C`），
但那会引入 u32 溢出风险，**必须先在实机上看这一步的效果再决定**。

### 怎么生成补丁固件

```sh
python tools/make_patched_firmware.py \
    --image  OLY_E_108_1800_0000_0000.BIN \
    --recipe patches/ep5_af_stepcap_pattern.json \
    --out    OLY_E_108_1800_0000_0000.AFSTEP.BIN
```

配方用的是**唯一字节模式**（不是硬编码偏移），所以对其它 E-P5 版本也成立；
命中数不等于 1 时工具会**直接拒绝**，不会瞎改。

**已实测输出**：

```
[OK] 容器往返逐字节一致（解码/再编码 == 原文件）
  cap-0x6cc    命中 1 处（期望 1） OK     @payload 0x002CA31A  runtime 0x4058A31A
  cap-0x1c20   命中 1 处（期望 1） OK     @payload 0x002CA2DA  runtime 0x4058A2DA
[自检] 重新解析输出：4 个块，全部块校验和自洽
新固件 SHA-256: 209379198f02539abe820a6ab9e9254f5ac70e972f291fc7e3b6e938e03daf2f
新固件大小     : 44826624   （与原文件同长）
```

> 本仓库**不收录**改过的固件镜像（固件著作权属 Olympus/Taiyo Yuden）。
> 上面的命令会在你自己的机器上生成它。

### 刷入

和第 1 步完全一样：改名成 `E1089999.BIN`，放进 `DCOLYMP/`，按住 `OK` 开机，等 AF 灯闪完。

### 怎么验收

- 相机正常开机、菜单可进、拍照正常 ⇒ 补丁没搞坏系统。
- AF 行为变化需要实拍对比（松下长焦端对焦行程 / 大范围合焦速度）。
- **不要**在没验证 v1.8 能刷成功之前就刷这个补丁。

---

## 4. 第 3 步 —— 取机身 mask ROM（**进行中**）

### 为什么需要它

「照片 10 项 / 录像 4 项」的菜单描述符在 **mask ROM `0x7E452BDC` / `0x7E452BE4`**，
滤镜算法与调校参数也全在 ROM 里。已确认：
**50 个固件映像 / 245 个块 / 59 个装载地址，0 个落在 `0x7Exxxxxx`**，
官方更新链路（41 组请求字段变体）**只发 1 个 `.BIN`** ⇒ ROM 不是通过固件更新的。

### 已经找到的最短路径：相机固件内置 `memdump`

E-P5 出厂固件的字符串池里有完整的文件系统调试 shell：

```
memdump NAME ADR LEN   - dump memory into file (ADR:hex,LEN:dec)
memload NAME ADR [LEN] - load memory from file (ADR:hex,LEN:dec)
```

只要能进这个 shell，`memdump ROM.BIN 0x7E452BD0 256` 就能把判据字节拷到卡上。

**当前阻塞**：这个 shell 的**分派代码不在块 0 内**（块 0 里搜不到任何指向那 0x130 字节
字符串区的指针/u32/半字对/PC 相对引用），输入通道未知。

### 备选：改固件插转储代码

- 固件更新路径本身就在读 SD 卡上的 `.BIN`（`[firmup]file_mount/ start.`），
  所以**改固件 → 卡刷**这条路是通的（社区改机补丁就是改过的 `.BIN`）。
- 需要：文件写 API 的地址与调用约定 + 一个能插入的钩子点 + 等长覆盖策略。
- `tools/make_patched_firmware.py` 已支持「等长覆盖 + 自动重算校验和」，只剩找地址。

### 如果 `memload` 可用（**最值得先试**）

`memload` 意味着固件认为那块内存**运行时可写**。若 `0x7Exxxxxx` 可写：

1. `memdump` 出 ROM → 分析；
2. `memload` 把新的菜单描述符 / 滤镜参数块**直接写进 ROM** ⇒
   「录像 10 项」「新增滤镜变体」从「判定不可行」变成「可做」。

判定方法：往一个无害的 ROM 地址写一个已知值，再 `memdump` 回读比对。

---

## 5. 三条路线对照

| 路线 | 动作 | 变砖风险 | 当前进度 |
|---|---|---|---|
| **A** | 进固件自带 shell，`memdump` | **无** | 🔄 入口待定位 |
| **B** | 改固件插转储代码 → 卡刷 | 中 | 🔄 工具已就绪，地址待找 |
| **C** | 刷 AF 步数上限补丁 | 中 | ✅ **可执行**（本手册 §3） |
| **D** | `memload` 试写 ROM | 视 ROM 是否可写 | 🔄 待实机判定 |

---

## 6. 需要你回传的信息

| # | 信息 | 用途 |
|---|---|---|
| 1 | 卡刷官方 v1.8 后 `[版本信息]` 的**确切字符串** | 确认对齐 |
| 2 | 卡刷过程中 AF 灯的实际表现 | 写进验收清单 |
| 3 | 相机 USB 连上 PC 后的设备名/驱动（MTP? PTP? 串口?） | 找 shell 输入通道 |
| 4 | 相机上有没有未暴露的 USB 之外的接口（HDMI? 扩展坞?） | 同上 |

---

## 7. 相关文档

| 文档 | 内容 |
|---|---|
| [`evidence/unlock/community_patch_A_semantics.md`](../evidence/unlock/community_patch_A_semantics.md) | 社区补丁两处改动的完整语义解码 |
| [`evidence/unlock/ep5_v1_8_patch_recipe.md`](../evidence/unlock/ep5_v1_8_patch_recipe.md) | E-P5 补丁配方与效果边界 |
| [`evidence/unlock/round22_maskrom_requirements_and_lensid.md`](../evidence/unlock/round22_maskrom_requirements_and_lensid.md) | mask ROM 依赖清单 R1–R12 |
| [`evidence/unlock/round23_official_channels_closed_and_rom_pipeline.md`](../evidence/unlock/round23_official_channels_closed_and_rom_pipeline.md) | 官方通道穷尽关闭的证据 |
| [`evidence/unlock/round24_camera_builtin_memdump.md`](../evidence/unlock/round24_camera_builtin_memdump.md) | 相机内置 `memdump`/`memload` 的发现 |
| [`tools/rom_fill_report.py`](../tools/rom_fill_report.py) | 拿到 ROM dump 后一条命令读出全部判据 |
