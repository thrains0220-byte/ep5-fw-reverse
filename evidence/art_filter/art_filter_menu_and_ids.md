# E-P5 艺术滤镜：ID 命名空间、菜单资源映射 与「录像形态被锁」的确切边界

> 日期：2026-10-22（第十四轮）
> 基线：**E-P5 v1.8**（`decoded/00_0100_402c0020.decoded.bin` 块 0，基址 `0x402C0000`，
> 15,728,576 B；`decoded/01_0101_427c0020.decoded.bin` 块 1，基址 `0x427C0020`，22,937,536 B）
> 交叉验证：**E-PM2 v1.6**（`fw-work/dec/epm2b/`，块 0 基址同为 `0x402C0000`）
> 方法：全块字符串扫描 + 正则提取 + 块 1 UTF-16LE 整池解码 + 结构化表解析。
> 性质：**静态观察**，不含执行证据。坐标一律给出 file offset 与 runtime address 两套。

---

## 0. 一句话结论

**E-P5 的艺术滤镜不是"一张 15 项的表"，而是「两套 ID 命名空间 × 13 个编译单元 × 两张 UI 菜单」。**
本轮把三件事一次性钉死：

1. **13 个滤镜实现模块**及其 **ID**，分属两套命名空间；
2. **照片艺术菜单 = 资源 ID `A03F`–`A048`（连续 10 项）**；
   **录像艺术菜单 = 资源 ID `A042`–`A045`（只有 4 项）**；
3. 块 0 里有一张 **99 条的「UI 字符串资源描述符表」**（ID `0x36`–`0x92` + `0x9D`–`0xA2`），
   每条指向机身 mask ROM 描述符 —— 这是"能不能加菜单项"的总闸门。

⇒ **"解锁被锁住的功能"最具体的目标已经出现：录像艺术菜单只有 4 项，照片菜单有 10 项，
差的那 6 项（Pop Art / Soft Focus / Pale&Light Color / Light Tone / Cross Process / Gentle Sepia）
在块 1 里已经有完整的多语言字符串，固件只是没把它们接进录像菜单。**

---

## 1. 观察 A —— 两套效果 ID 命名空间，13 个实现模块

固件把每个滤镜模块的任务名写成 `art_<kind>_<ID>_<name>`。
这个命名把 **ID 直接编进了字符串**，是唯一不依赖执行即可拿到的 ID↔名字映射。

### 命名空间 A：`art_effect_<NN>_<name>`（ID 为十进制×10 的整数）

| ID | 名字 | 模块源文件串（runtime） |
|---|---|---|
| 10 | `star_light` | `art_effect_10_star_light.c` @ `0x407151A4` |
| 20 | `pinhole` | `art_effect_20_pinhole.c` @ `0x40715715` |
| 30 | `frame` | `art_effect_30_frame.c` @ `0x40715B3C` |
| 40 | `soft_focus` | `art_effect_40_soft_focus.c` @ `0x407160EC` |
| 50 | `white_edge` | `art_effect_50_white_edge.c` @ `0x40716460` |

### 命名空间 B：`art_filter_<HH>_<name>`（ID 为十六进制）

| ID | 名字 | 模块源文件串（runtime） |
|---|---|---|
| `0x06` (6) | `rough_monochrome` | `art_filter_06_rough_monochrome.c` @ `0x40716B09` |
| `0x09` (9) | `diorama` | `art_filter_09_diorama.c` @ `0x407170F5` |
| `0x0E` (14) | `gentle_sepia` | `art_filter_0e_gentle_sepia.c` @ `0x40717513` |
| `0x14` (20) | `dramatic_tone` | `art_filter_14_dramatic_tone.c` @ `0x40717AE8` |
| `0x19` (25) | `artclearline` | `art_filter_19_artclearline.c` @ `0x40718275` |
| `0x1C` (28) | `mirror` | （同段，见下表备注） |
| `0x1D` (29) | `composite` | `art_filter_1d_composite.c` @ `0x407188E7` |
| `0x21` (33) | `pastel_art`（源文件名写作 `pastelart`） | `art_filter_21_pastelart.c` @ `0x40718CC8` |

另有 3 个公共编译单元：`art_filter_com.c` @ `0x407199A1`、`art_nr.c` @ `0x4071A72B`、
`art_stl2ycc.c` @ `0x4071AADD`。

### 1.1 两机型交叉验证

同一套 ID 在 **E-PM2 v1.6** 与 **E-P5 v1.8** 上完全一致，只有地址平移
（v1.6 的 art 模块在 `0x406F5000`–`0x406FC000`，v1.8 在 `0x40714000`–`0x4071B000`）。

⇒ **推断**：这是 Olympus 产品线通用的滤镜 ID 空间，跨机型、跨版本稳定；
块 0 里不存在"某机型专属的滤镜 ID"。

### 1.2 重要边界（修正上一轮的一处误解）

第十三轮曾把 `art_effect_10/20/30/40/50` 判定为"录像侧命名空间"。
**该判断不成立**：`star_light`、`pinhole`、`frame`、`soft_focus`、`white_edge`
在块 1 里的 UI 名字与照片菜单同处一个 ID 段（见 §3），
并且 `soft_focus`（`A041`）明确出现在**照片**菜单里。
⇒ **两个命名空间是"实现分家"，不是"拍照/录像分家"。**
真正区分拍照/录像的是 §2 的 `MODE_EXPOSE` / `COLORTONE` 列表与 §3 的两张菜单。

---

## 2. 观察 B —— `MODE_EXPOSE` 与 `COLORTONE` 两张模式枚举表

### 2.1 `MODE_EXPOSE_<name>`（属 `mov_art.c`）

`mov_art.c` 源文件串在 `0x406B18xx` 附近（v1.6）/ v1.8 同段。
其字符串表是一串 NUL 分隔的名字，**每一项都有一个 `_MOVIE` 孪生**：

```
POPART  FANTASIC_FOCUS  DAYDREAM  LIGHT_TONE  ROUGH_MONOCHROME  TOY_PHOTO
MINIATURE  CROSS_PROCESS  CROSS_PROCESS_2  GENTLE_SEPIA  DRAMATIC_TONE
DRAMATIC_TONE_2  FISH_EYE  DRAWING  TENDER_LIGHT  ROCK  CRYSTAL
WATERCOLOR  MIRROR  COMPOSITE  LIGNE_CLAIR  PASTEL
```

- **录像变体（`_MOVIE`）恰好 22 项**，与上表 22 项一一对应；
- 照片变体 31 项 = 22 项 + 9 项非滤镜场景模式
  （`BULB / PANORAMA / BEAUTY / 3D / MINIATURE_JUDGE_NG / PANORAMA_JUDGE_NG /
   3D_JUDGE_NG / BEAUTY_JUDGE_NG / PREVIEW`）。

⇒ **观察**：这个枚举把"创意模式"与"BULB/PANORAMA/BEAUTY/3D"等场景模式混编在同一个编号空间，
`_MOVIE` 孪生只对 22 个创意模式存在。
**推断**：`MODE_EXPOSE` 就是**机身创意/场景模式的总枚举**，22 项创意模式即固件支持的
**全部 22 个创意模式 ID**（不是 10、也不是 13）。

> 与 §1 的 13 个实现模块对照：22 个模式里只有 13 个在 E-P5 有专属像素实现模块，
> 其余 9 个（POPART / FANTASIC_FOCUS / DAYDREAM / TOY_PHOTO / CROSS_PROCESS /
> CROSS_PROCESS_2 / FISH_EYE / DRAWING / TENDER_LIGHT / ROCK / CRYSTAL / WATERCOLOR /
> LIGNE_CLAIR）大概率**复用同一套基础算子**（色彩矩阵 + 曲线），无需专属 pass 链。
> **这一点是推断，未取得像素级证据。**

### 2.2 `COLORTONE_<name>` 定宽名字表（26 字节/项）

v1.8 位于 `0x40AB1143` 起的定宽记录区。**共出现 3 份内容不同/顺序不同的列表**：

| # | 内容 | 项数 |
|---|---|---|
| ① | `NONE VIVID NATURAL FLAT PORTRAIT MONOTONE IFINISH` + `POPART TOY_PHOTO SOFT_FOCUS DAYDREAM GRAINY_FILM LIGHT_TONE DIORAMA CROSS_PROCESS GENTLE_SEPIA DRAMATIC_TONE LIGNE_CLAIR PASTEL` | 19 |
| ② | 同 ① | 19 |
| ③ | `NONE` + **`SOFT_FOCUS POPART DAYDREAM LIGHT_TONE TOY_PHOTO GRAINY_FILM`** + `DIORAMA CROSS_PROCESS GENTLE_SEPIA DRAMATIC_TONE LIGNE_CLAIR PASTEL` | 13 |

- ① / ② = **照片侧**色彩色调表：前 7 项是基础色彩模式（无 / 鲜艳 / 自然 / 平坦 / 人像 / 单色 / 留白），
  后 12 项是艺术滤镜。
- ③ = **录像侧**色彩色调表：同样 12 个艺术滤镜，但**前 6 项被重排到最前**
  （`SOFT_FOCUS POPART DAYDREAM LIGHT_TONE TOY_PHOTO GRAINY_FILM`）。

⇒ **观察**：录像色彩色调列表比照片列表**少了 6 个色彩模式**（VIVID/NATURAL/FLAT/PORTRAIT/MONOTONE/IFINISH），
艺术滤镜部分则是**同一套 12 个**、只是顺序不同。
⇒ **推断**：顺序差异对应**录像菜单的显示顺序**，与 §3 中录像菜单只有 4 项的现象互为印证。

### 2.3 `COLORTONE` 12 项 ↔ `MODE_EXPOSE` 22 项 ↔ §1 的 13 个模块

| COLORTONE 12 项 | MODE_EXPOSE 中同名项 | §1 中有专属实现模块？ |
|---|---|---|
| POPART | POPART | ✘ |
| TOY_PHOTO | TOY_PHOTO | ✘ |
| SOFT_FOCUS | — （FANTASIC_FOCUS 不同名） | ✔ `art_effect_40` |
| DAYDREAM | DAYDREAM | ✘ |
| GRAINY_FILM | — （无同名） | ✘ |
| LIGHT_TONE | LIGHT_TONE | ✘ |
| DIORAMA | MINIATURE（= 移轴同名） | ✔ `art_filter_09` |
| CROSS_PROCESS | CROSS_PROCESS | ✘ |
| GENTLE_SEPIA | GENTLE_SEPIA | ✔ `art_filter_0e` |
| DRAMATIC_TONE | DRAMATIC_TONE | ✔ `art_filter_14` |
| LIGNE_CLAIR | LIGNE_CLAIR | ✘ |
| PASTEL | PASTEL | ✔ `art_filter_21` |

另有 §1 中在 COLORTONE 里没有的：`star_light(10)`、`pinhole(20)`、`frame(30)`、
`white_edge(50)`、`rough_monochrome(06)`、`artclearline(19)`、`mirror(1c)`、`composite(1d)`。

⇒ **结论**：固件里存在 **3 个互不相同的滤镜名字集合**（13 模块名 / 22 模式名 / 12 色调名），
它们是同一批滤镜的**三个不同视角**，不是三批滤镜。任何"滤镜总数"的说法都必须指明是哪个集合。

---

## 3. 观察 C —— 块 1 的资源 ID ↔ UI 名字精确映射（关键）

### 3.1 方法

块 1 的 UI 字符串形如 `@A042@Grainy Film`：`@Axxx@` 是**内嵌在字符串体内的资源 ID 标记**，
同一 ID 在每个语言分区各出现一次。整池按 UTF-16LE 解码后用
`@([A-Z][0-9A-F]{2,4})@` 切分，**要求标记之后的文本整串等于某个滤镜名**
（避免抓到相邻串的残留标记 —— 第十三轮的 `block1_filter_names.json` 就是因为
按偏移邻接取值而产生了「A042 = Grainy Film 且 = Pale&Light Color」的假冲突）。

### 3.2 照片艺术菜单（英文分区，`0x35021E`–`0x350C2E`）

| 资源 ID | UI 名 |
|---|---|
| `A03F` | Pop Art |
| `A040` | Dramatic Tone |
| `A041` | Soft Focus |
| `A042` | Pale&Light Color |
| `A043` | Light Tone |
| `A044` | Grainy Film |
| `A045` | Pin Hole |
| `A046` | Diorama |
| `A047` | Cross Process |
| `A048` | Gentle Sepia |

**连续 10 项，与第十三轮"菜单只暴露 10 个"一致。**

### 3.3 录像艺术菜单（`0x3567DC`–`0x356F70`）

| 资源 ID | UI 名 |
|---|---|
| `A042` | Grainy Film |
| `A043` | Pin Hole |
| `A044` | Diorama |
| `A045` | Dramatic Tone |

**只有 4 项。**

⇒ **观察（硬证据）**：同一批资源 ID 在**录像菜单语境**下只挂出了 4 个艺术滤镜，
比照片菜单少 6 个：**Pop Art / Soft Focus / Pale&Light Color / Light Tone / Cross Process / Gentle Sepia**。
这 6 个的字符串在块 1 里**已经存在**（照片菜单分区里有），只是没被录像菜单引用。

> **推断（高置信）**：这就是"电影艺术滤镜被锁"在 **UI/资源层**的表现形态。
> 它与第十一轮在 **代码层**找到的锁点（`0x40788A5E` 录像形态锁、
> `0x602AEB94` 类型位掩码）是**同一个功能的两层**。

### 3.4 其它已占用 ID（同一 ID 空间）

| ID | 名字 | 备注 |
|---|---|---|
| `A021` | i-Enhance | |
| `A033` | Muted | |
| `A04D` | Monotone | **不是空位** |
| `A04F` | MF（MF 辅助说明文字） | **不是空位** |
| `A07A`/`A07D` | Vivid | 两个分区 |
| `A07B`/`A07E` | Natural | 两个分区 |
| `A07C`/`A07F` | Portrait | 两个分区 |
| `A087`/`A088`/`A089` | Vivid / Natural / Portrait | 录像侧分区 |

### 3.5 对第十三轮结论的修正

| 第十三轮说法 | 本轮核实结果 | 状态 |
|---|---|---|
| `A04F` 是 `A03F`–`A05F` 区间唯一空缺资源 ID | `A04F` = "MF" 辅助文字；**空闲的是 `A049`/`A04B`/`A04C`/`A04E`** | ❌ 修正 |
| 4 个已实现滤镜（Star Light / White Edge / Pastel / Clear Line）"名字已在块 1" | v1.8 块 1 里 `Clear Line` **0 次**；`Star Light`/`White Edge` 仅出现在**长句**中（如 "Add Effects @A016@"），**没有独立菜单串与 ID** | ❌ 修正 |
| 实现 15 / 菜单 10 / 4 个无位置 | 实现 **13** 个模块（§1）/ 照片菜单 **10** / 录像菜单 **4** | ⚠️ 重新表述 |

⇒ **实务影响**："给隐藏滤镜加菜单项"这条路**比原先设想的窄**：
块 1 里**没有现成的 `Star Light` / `White Edge` / `Pastel` 独立菜单串**可借用，
必须**等长替换**（把某个不用的同长度名字原位改写）或**借用主文本池零填充段**新建。

---

## 4. 观察 D —— 块 0 的「UI 字符串资源描述符表」

### 4.1 结构

```
rt 0x402D8BEC  (file 0x18BEC)   记录长度 28 字节, 共 99 条
+0x00 u32  resource_id      0x36..0x92 (连续 57 项) 后跳到 0x9D..0xA2 (6 项)
+0x04 u32  0
+0x08 u32  0
+0x0C u32  mask_rom_ptr     0x7E______ —— 机身 mask ROM 里的描述符
+0x10 u32  type             11 / 4 / 12 / 10 / 9 / 7 …
+0x14 u32  flags            位标志
+0x18 u32  0
```

艺术滤镜段（ID `0x3F`–`0x48`）：

| ID | runtime | mask ROM 描述符 | type | flags | UI 名（§3.2） |
|---|---|---|---|---|---|
| `0x3F` | `0x402D8CE8` | `0x7E33628C` | 11 | 0x400 | Pop Art |
| `0x40` | `0x402D8D04` | `0x7E5C7378` | 11 | 0x800 | Dramatic Tone |
| `0x41` | `0x402D8D20` | `0x7E2AC88A` | 11 | 0x600 | Soft Focus |
| `0x42` | `0x402D8D3C` | `0x7E2A8BD9` | 4 | 0x600 | Pale&Light Color / 录像 Grainy Film |
| `0x43` | `0x402D8D58` | `0x7E2B0EED` | 4 | 0x600 | Light Tone / 录像 Pin Hole |
| `0x44` | `0x402D8D74` | `0x7E2B1117` | 4 | 0x600 | Grainy Film / 录像 Diorama |
| `0x45` | `0x402D8D90` | `0x7E13BA1E` | 11 | 0x800 | Pin Hole / 录像 Dramatic Tone |
| `0x46` | `0x402D8DAC` | `0x7E247F78` | 4 | 0x600 | Diorama |
| `0x47` | `0x402D8DC8` | `0x7E24D96E` | 4 | 0x800 | Cross Process |
| `0x48` | `0x402D8DE4` | `0x7E25ECC4` | 4 | 0x800 | Gentle Sepia |

### 4.2 结论与边界

- **观察**：ID `0x93`–`0x9C`（10 个）在表里**没有记录**。
- **观察**：描述符表本身在块 0，但 **Ghidra 全量引用扫描对该表首项 `0x402D8BEC`
  与三个条目地址（`0x402D8CEC`/`0x402D8D04`/`0x402D8D04`）均为 0 处引用**
  ⇒ 该表通过**基址寄存器 + 位移**或经由 **mask ROM 的指针表**间接寻址。
- **观察**：块 0 内**找不到**按字节排列的菜单 ID 列表
  （`3F 40 41 … 48` 与 `42 43 44 45` 的全部命中都是十六进制调试字符表，非数据）。
- **推断**：mask ROM 指针指向的描述符里含"该资源对应哪些菜单项、显示什么"，
  因此**菜单项的组成很可能在 mask ROM 里**（不可通过固件更新改写）。
- **未知**：录像菜单为何只列 4 项 —— 是 mask ROM 描述符里的列表短，
  还是块 0 侧的 `flags` 门控，**尚未判定**。这是下一步的决定性问题。

> **对"新增滤镜"的最终含义（第十四轮结论）**：
> 在**块 0 一侧**能改的只有描述符表的 `flags` / `type` 字段与指向关系；
> **菜单项的清单本身在 mask ROM**。
> 因此"新增一个菜单项"在**没有实机 mask ROM dump** 的前提下不可完成；
> 可完成的是「**解锁既有项**」（把某个已有 ID 的描述符/flags 指到另一个 mask ROM 描述符）
> 与「**参数变体**」（改 RAM 里的 312 B 参数块）。

---

## 5. 对用户两个目标的直接回答

### 4.5 滤镜「子 ID → 处理函数」的分派表在 mask ROM（第十四轮续补）

艺术簇里的 `FUN_40788DEE`（`rt 0x40788DEE`）有一段**从 mask ROM 取函数指针并间接跳转**的代码：

```c
if (cVar1 == '\x02') {
  uVar8 = *(uint16 *)(*(int *)(param_1 + 4) + 4);
  if (uVar8 < 0x2001) {
    iVar6 = (uVar8 & 0xf) * 8;
    if (*(uint32 *)(iVar6 + 0x7e897cf4) == uVar8) {
      UNRECOVERED_JUMPTABLE = *(code **)(iVar6 + 0x7e897cf8);
      (*UNRECOVERED_JUMPTABLE)(...);      /* ← mask ROM 里的处理函数 */
    }
  }
}
```

⇒ **观察**：这是一张 **16 槽 × 8 字节**的表 @ **mask ROM `0x7E897CF4`**
（`[i]` = 该槽的 ID 值，`[i+4]` = 处理函数指针），
用 `id & 0xF` 索引 —— 即**按滤镜 ID 的低 4 位分派**。

⇒ **结论（重要边界）**：
**「哪个 ID 对应哪个实现」的决定权在机身 mask ROM，不在固件块 0。**
块 0 里只放**实现**（本轮清点的 13 个模块），
**"还有哪些 ID 可用、哪个 ID 映射到哪个实现" 要靠实机 mask ROM dump 才能全知。**

> 补充：艺术簇（`0x40788300`–`0x40789600`）里对 `0x605FCD3C`（效果 ID 全局）
> 的比较**只出现在 ID 10 / 14 / 50**（`FUN_4078846D` / `4078849B` / `40788562` /
> `407885F9` / `40788AFC` / `40788CAC` / `40788D18` / `40788DEE`），
> 其余 10 个滤镜的 ID 比较**不在块 0** —— 与上面的 mask ROM 分派表结论一致。

### 目标①：新增创意滤镜

| 路线 | 可行性 | 依据 |
|---|---|---|
| 全新像素算法 | ❌ | 算法与调校参数在机身 mask ROM（第十一轮已证） |
| 给已有效果做参数变体 | ✅ | `0x605FCD44` / `0x605FCE7C` 两个 312 B RAM 参数块，固件侧可改写（第十一轮） |
| 新增一个菜单项指向既有实现 | ⚠️ 受限 | 需同时解决「块 1 字符串槽位」+「块 0 资源描述符」两处；`A049/A04B/A04C/A04E` 是空闲 ID，但**描述符在 mask ROM** |
| 把 13 个模块里"已实现但菜单无位置"的挂进菜单 | ⚠️ 受限 | 块 1 无现成的独立菜单串可借用，只能等长替换 |

### 目标②：解锁被锁住的功能

**最具体的落点（资源层）**：录像艺术菜单只有 4 项，差 6 项。
**代码层**：第十一轮已定位 `0x40788A5E`（录像形态锁）与 `0x602AEB94`（类型位掩码）。

**⇒ 最小可行解锁路径（推断，待验证）**：
1. 代码层：放开 `0x602AEB94` 的录像类型位 + `FUN_40788616` 的 `param_1 == 2` 分支；
2. 资源层：把录像菜单列表从 4 项扩到 10 项 —— 需要 mask ROM 描述符支持，
   **这是唯一的硬阻塞**，必须靠实机 mask ROM dump 才能确认。

---

## 6. 复现

```sh
# 艺术滤镜全清单（两套命名空间 + 模块 + 两张模式表）
python tools/gen_art_inventory.py --blk0 decoded/00_0100_402c0020.decoded.bin \
    --out evidence/art_filter/art_inventory_v18.json

# 块 1 资源 ID ↔ 艺术滤镜名
python tools/block1_art_id_map.py --blk1 decoded/01_0101_427c0020.decoded.bin
python tools/block1_art_id_dump.py --blk1 decoded/01_0101_427c0020.decoded.bin

# 块 0 UI 资源描述符表
python tools/parse_res_desc_table.py --blk0 decoded/00_0100_402c0020.decoded.bin \
    --json evidence/art_filter/res_desc_table_v18.json

# 块 1 全部资源 ID（任意 ID）
python tools/block1_res_id_map.py --blk1 decoded/01_0101_427c0020.decoded.bin
```

---

## 7. 未知 / 未覆盖

1. **录像菜单 4 项 vs 照片 10 项的成因**未判定（mask ROM 描述符 vs 块 0 flags）。
2. `MODE_EXPOSE` 的 22 项与 `COLORTONE` 的 12 项之间**缺少 ID 数值映射**。
   `mov_art.c`（源文件串 `0x406B2000`）尾部确有一张 **16 字节记录表**，
   E-P5 v1.8 起始 `rt 0x406B1D10`（file `0x3F1D10`），字段为
   `{u32 id, u32 flags, u32 type, u32 mask_rom_ptr}`：
   ```
   0x406B1D10  id=70    flags=0  type=512  rom=0x7E4F287C
   0x406B1D20  id=79    flags=0  type=512  rom=0x7E4F288F
   0x406B1D30  id=581   flags=3  type=512  rom=0x7E4F28A8
   0x406B1D40  id=590   flags=3  type=512  rom=0x7E4F28C3
   0x406B1D50  id=71    flags=0  type=512  rom=0x7E4F28E4
   0x406B1D60  id=80    flags=0  type=512  rom=0x7E4F28F9
   0x406B1D70  id=72    flags=0  type=512  rom=0x7E4F2914
   0x406B1D80  id=81    flags=0  type=512  rom=0x7E4F292B
   0x406B1D90  id=65866 flags=2  type=512  rom=0x7E4F2948
   0x406B1DA0  id=66131 flags=3  type=512  rom=0x7E4F2965
   0x406B1DB0  id=585   flags=3  type=0    rom=0x7E4F2988
   0x406B1DC0  id=16777810 flags=3 type=0  rom=0x7E4F299E
   ```
   两机型（v1.6 / v1.8）结构完全一致。
   **未判定**：`id` 字段与 `MODE_EXPOSE` 名字表的配对关系
   （`id` 出现 0x1012A / 0x1000252 这类异常值，疑为两个 u16 字段而非单一 u32）。
3. `art_filter_1c_mirror`（ID `0x1C`）**没有 `.c` 源文件串**（其余 12 个模块都有）——
   固件自身的命名不一致，非工具漏检；其字符串为
   `art_filter_1c_mirror` @ `0x407185FC` / `art_mirror_pass1|pass2|pass_err`。
4. 13 个模块的**像素实现函数地址**仍未逐个定位
   （模块名目录无配套地址表，已用 21 项函数指针数组搜索证伪，见 §8）。
5. 无实机，mask ROM（`0x7E000000`–`0x7FFFFFFF`）内容不可读。
