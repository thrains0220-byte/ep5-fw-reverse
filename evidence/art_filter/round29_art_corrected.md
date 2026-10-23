# 第二十九轮：艺术滤镜 —— 接受实机更正 + 重新定位（关键更正轮）

> 触发：**用户实机反馈**「E-P5 的 ART 照片一共 12 个，视频也能用上这 12 个」。
> 这条反馈推翻了第 22 / 27 / 28 轮的核心叙事模型，必须正式更正。
> 证据分级同前：**观察** / **推断** / **未知**。

---

## 0. 被推翻的结论（正式作废）

| 原结论 | 出处 | 处置 |
|---|---|---|
| 「ART 照片 10 项、录像 4 项」 | 第 22 轮 R1/R2 标注、第 27/28 轮叙事 | **作废**。实机：照片 12 项，录像同为 12 项 |
| 「`MOV 0xa,D0` = 照片侧 10 个滤镜」 | 第 28 轮我的解读 | **作废**。`0x0A` 是**默认效果索引**（见 §2.1），不是数量 |
| C1（类型码 4→0） | 第 27 轮 | **撤回**。前提是「改类型码能换滤镜清单」；实机证明清单不分照片/录像，改类型码只会改拍摄模式分组 |
| C2 / C3（录像槽表改指 / 类型码+槽表） | 第 27 轮 | **撤回**。① 前提已被第 28 轮证伪（那张表在 XMP/EXIF 区）；② 「照片/录像清单不同」的前提也作废 |
| D2 / D3（电影 ART 描述符改指照片 ART） | 第 28 轮 | **撤回**。前提 = 「mode 2 是电影艺术、mode 6 是照片 ART、两者清单不同」；实机证明两者相同 |
| 「ART 菜单显示名在 ROM」 | 第 28 轮中途的推断 | **再推翻**：菜单名在**块 1（语言资源包）**，在 `.BIN` 里（见 §3） |

⇒ SD 卡目录已同步处理：`C1/C2/C3` 目录改名加「已撤回」前缀，`D2/D3` 目录已删除；
仓库里 `patches/ep5_art_moviemode_pattern.json` 与 `ep5_art_typegate_moviemode.json`
加了 `"withdrawn"` 字段并停止产出固件。**目前唯一保留待测的固件是 D1（解除类型闸门）**。

---

## 1. 正确的架构（观察）

```
ROM (0x7E 区, 不在 .BIN)
   │  ├─ 决定「ART 菜单显示哪几项」        ← 清单/选择逻辑在 ROM
   │  ├─ art_get_filterlist_tbl / art_get_dramatic_tone_addr / art_get_ldata_size
   │  └─ 回调 CPU0：FUN_403E7B1B / 79 / C3F、类型掩码 0x602AEB94
   ▼
块 0 (在 .BIN, 可改)
   ├─ 13 个滤镜的像素实现（art_filter_XX / art_effect_XX）
   ├─ 22 套 MODE_EXPOSE_* 曝光预设
   ├─ 参数装载：照片 FUN_407868FC(0x605FCA00, 0x7E5C9809) / 录像 FUN_407BC0BE(0x605FCCC4, 0x7E8973D0)
   ├─ 类型闸门：FUN_40788616 / FUN_4078866A（读 0x602AEB94）
   └─ 「Major ROM Address」分区表里含 artfill_addr / arteffe_addr
块 1 (在 .BIN, 可改)  语言资源包：ART 菜单显示名（中/英/日…各一包）
```

**一句话**：**清单在 ROM，名字在块 1，实现与预设在块 0。**
⇒ 能「改名字 / 改已有滤镜的表现」，不能「凭空多出一个菜单项」。

---

## 2. 13 个滤镜实现（观察；ID 是十六进制，第 28 轮按十进制解析错了）

| ID | 实现 | 字符串地址 | ID | 实现 | 字符串地址 |
|---|---|---|---|---|---|
| 0x06 | rough_monochrome | 0x40716794 | 0x1C | mirror | 0x407185FC |
| 0x09 | diorama | 0x40716EE0 | 0x1D | composite | 0x4071877C |
| 0x0E | gentle_sepia | 0x407173A0 | 0x20 | pinhole | 0x407155B0 |
| 0x10 | star_light | 0x40714EF4 | 0x21 | pastel_art | 0x40718A94 |
| 0x14 | dramatic_tone | 0x4071771C | 0x30 | frame | 0x40715888 |
| 0x19 | artclearline | 0x40717FA4 | 0x40 | soft_focus | 0x40715F1C |
| | | | 0x50 | white_edge | 0x407162F8 |

**13 个实现 vs 用户看到的 12 项** ⇒ 极可能只差一个（例如 `white_edge` 白边是另一功能的描边，不是 ART 菜单项）。
**未知**：哪个没上菜单。

### 2.1 `0x0A` 的真实含义（更正第 28 轮）

`MOV 0xa,D0` 出现在 `0x40788462 / 0x4078850C / 0x407885B9 / 0x40788603`，
都是「设置当前效果索引」的调用（`CALL FUN_407887E0`，该函数写 `0x605FCD3C`）。
⇒ **0x0A = 默认效果索引（十进制 10 = 0x0A，对应 ID 0x10 star_light 附近）**，
**不是滤镜数量**。同类的还有 `CMP 0x32,D0`（0x32 = 50 = `white_edge` 的 ID）与 `MOV 0x11/0x10/0x0F/0x0D/0x0C,D0`
（`FUN_4078831F/41/63/91/AE` 的一组命令码 0x0C/0x0D/0x0F/0x10/0x11）。

**推断**：这组命令码是「艺术效果子命令 ID」，`0x0C/0x0D/0x0F/0x10/0x11` 各自对应一个滤镜的触发动作
（与实现的 ID 0x09/0x0E/0x10/0x14/0x19… 对不上号，说明命令码与滤镜 ID 是两套编号）。

---

## 3. ★ ART 菜单显示名在块 1（观察）

块 1 = 语言资源包（25 份，每份 50–115 KB，UTF-16LE）。命中示例：

英文包（资源 0x42B0EA00 起）：
```
0x42b0ec2a 'Cross Process'      0x42b0ec46 'Diorama'
0x42b0ec56 'Dramatic Tone'      0x42b0ec72 'Gentle Sepia'
0x42b0ec8c 'Grainy Film'        0x42b0eca4 'Light Tone'
0x42b0ecba 'Pale&Light Color'   0x42b0ecdc 'Pop Art'
0x42b0ecec 'Soft Focus'         0x42b0ed02 'Pin Hole'
```
中文包（资源 0x42A8E000 起）同样命中：鲜艳色调 / 颗粒胶片 / 交叉冲印 / 黑白 / 复古胶片 /
针孔 / 高调 / 棕褐色 / 水彩(画) / 粉彩 / 暗角 / 戏剧色调 / 柔焦 / 立体效果 / 流行色彩 /
古典色调 / 淡雅色调 / 淡雅色彩 / 绘画 / 梦幻 / 鱼眼 / 镜面 …

菜单项带编号前缀：`@A03F@Pop Art`、`@A041@Soft Focus`、`@A042@Grainy Film`、
`@A043@Pin Hole`、`@A044@Grainy Film`、`@A045@Pin Hole`、`@A047@Cross Process`、
`@A04D@Monotone`、`@A033@Pastel`、`@A077@Watercolor`。
⇒ **`@A0xx@` 是菜单项资源编号**，可用来精确定位 ART 菜单项。

**注意**：块 1 里出现的这一组名字是 **E-M1 II/III 那一代**的完整艺术滤镜集
（Diorama / Dramatic Tone / Gentle Sepia / Light Tone / Pale&Light Color / Pop Art / Soft Focus …），
E-P5 只露出其中一部分（用户看到 12 项）。

---

## 4. ★ ARTFIL 分区会被固件更新写入（观察）

块 0 固件更新流程串：
```
0x405F25FA  '[firmup]...ARTFIL Gets'
0x405F294D  '[firmup]TYPE_FIRMUP_WRITE_ARTFIL'
```
加上第 26 轮的分区清单（USR OSD PIC WAV FRAME ADJSLF **ARTFIL** NOREXE C3D GUIDE **BEAUTY** …）
⇒ **ARTFIL 是固件更新可写分区**。若艺术滤镜的运行时数据（参数/曲线）落在 ARTFIL，
那么**官方 .BIN 之外的路径（自己构造 ARTFIL 镜像）也可能可写**。
**未知**：本次 4 个块（0x100 代码 / 0x101 资源 / 0x104 JPEG / 0x106 载荷）分别对应哪个分区，
ARTFIL 是否就是 0x101。

---

## 5. 「选哪 12 项」的清单不在 .BIN 里（观察）

对 4 个块全部做「升序、且命中 ≥8 个已知滤镜 ID 的字节簇」搜索：**0 命中**。
⇒ 菜单项的选择/裁剪不是 `.BIN` 里的 ID 表，**在 ROM 侧**。

另外块 0 有 `ArtFilter:0x%02x(%d)`（`0x406BF6BC`）、`ArtFilterMode:`（`0x406B83EC`）、
`api_rec_Get_Art_Filter_Progress`（`0x4068A229`）—— ArtFilter ID 是 1 字节。

---

## 6. 块 0 里的曲线型数据（观察，尚未归属到具体滤镜）

块 0 中找到的非递减 u8 斜坡（候选增益/色调表）：
```
0x402E6FE0  len=32768   00 00 … ff ff      ← 32 KB 单调斜坡
0x402EF048  len= 3992   00 00 ff ff …
0x402CE7C5  len= 2075   00 00 … ff ff
0x402CE1F0  len=   64   00 … 01 02 04 08 10 20 40 80   ← 位标志斜坡
```
**未知**：哪一段对应哪个滤镜；「LUT 直出」是否就是替换其中一段。

---

## 7. 本轮后的路线状态

| 路线 | 状态 |
|---|---|
| **新增第 13 个滤镜条目** | **不可**（清单在 ROM）。除非拆机 dump ROM 或进调试 shell |
| **改写已有滤镜的表现** | **可行**（13 个实现在块 0）→ 这是「LUT 直出」的现实形态 |
| **改 ART 菜单显示名** | **可行**（名在块 1，UTF-16LE，等长覆盖即可）→ 可做「森山大道」式的自定义命名 |
| **解除类型闸门 D1** | 仍待实机验证（前提未被推翻，但预期收益已下调） |
| **R-5 计算摄影限制** | 未推进 |

---

## 8. 需要用户配合的一条信息（很便宜，但很关键）

**请把相机 ART 菜单里那 12 项的名字念出来（或拍照）。**
有了这 12 个名字，我就能：
1. 对上块 1 里的字符串 + `@A0xx@` 资源编号；
2. 反查每个名字对应块 0 的哪个实现 ID（0x06/0x09/0x0E/0x10/0x14/0x19/0x1C/0x1D/0x20/0x21/0x30/0x40/0x50）；
3. 找出**多出来的那 1 个实现**（13 − 12）是谁 —— 它就是「隐藏滤镜」的最强候选；
4. 立刻做「改名」与「改写某个滤镜表现」两个可刷补丁。

---

## 9. 复现

```bash
python tools/art_subsystem_scan.py registry --block decoded/00_0100_402c0020.decoded.bin
python fw-work/find_cn_names.py        # 中文滤镜名定位
python fw-work/dump_langpack.py        # 语言包整段字符串
python fw-work/find_id_list_table.py   # 搜“选哪 12 项”的 ID 表（全块 0 命中）
python fw-work/find_curves.py          # 搜曲线/增益表
```
