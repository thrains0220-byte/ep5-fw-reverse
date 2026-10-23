# 跨机型艺术滤镜菜单资源 ID 图谱 —— 「录像 4 项 vs 照片 10 项」的性质判定

> 日期：2026-10-23（第十九轮）
> 覆盖：11 份已解码块 1（E-P5 / E-M10 II ×2 / E-M5 II / E-M1 v4.6 / E-M1 II v3.0 / E-M1 III / E-M5 III / E-M10 III / E-PL9 / PEN-F）
> 工具：`tools/block1_art_menu_survey.py`、`tools/cross_model_art_menu_ids.py`
> 产出：`evidence/art_filter/cross_model_art_menu_ids.json`
> 性质：**观察（静态）**。

---

## 0. 结论（两条，都改变项目目标的性质）

### 结论 1 —— 照片艺术菜单是**固定的 10 项**，所有机型名字与顺序完全一致

```
Pop Art → Dramatic Tone → Soft Focus → Pale&Light Color → Light Tone
→ Grainy Film → Pin Hole → Diorama → Cross Process → Gentle Sepia
```

| 机型 | 照片菜单资源 ID 段 | 与标准段的偏移 |
|---|---|---|
| E-M1 II v3.0 / E-M1 III v1.2 / E-M5 II v4.1 / E-M5 III v1.4 / E-M10 II v1.4 / E-M10 III v1.2 | `A032`–`A03B` | 0 |
| E-M1 v4.6 | `A035`–`A03E` | +3 |
| **E-P5 v1.8** | **`A03F`–`A048`** | **+13** |

⇒ 照片菜单**没有缺项**，不需要"补齐"；E-P5 只是整段后移。

### 结论 2 —— ★ 录像艺术菜单的项数**逐机型不同**，且 **Olympus 在多款机型上确实做过 10 项**

| 机型 | 年份 | 录像菜单资源 ID 段 | 项数 | 名字 |
|---|---|---|---|---|
| E-M1 II v3.0 | 2015 | `A073`–`A07C` | **10** | Pop Art…Dramatic Tone |
| E-M1 III v1.2 | 2016 | `A073`–`A07C`（部分） | ~10 | 同名单 |
| E-M5 III v1.4 | 2016 | `A062`–`A06B` | **10** | 同名单 |
| E-M10 III v1.2 | 2017 | `A05A`–`A063` | **10** | 同名单 |
| E-M5 II v4.1 | 2017 | `A041`–`A045` | 5 | Monotone + 4 |
| E-M10 II v1.4 | 2018 | `A041`–`A045` | 5 | Monotone + 4 |
| E-M1 v4.6 | 2019 | `A042`–`A045` | 4 | Grainy Film / Pin Hole / Diorama / Dramatic Tone |
| **E-P5 v1.8** | 2013 | **`A042`–`A045`** | **4** | 同上 4 项 |

⇒ **「录像 10 项艺术滤镜」是原厂在 2015–2017 多款机型上做得到的功能。**
⇒ E-P5 的 4 项是**该机型的配置选择**，不是产品线能力上限。

---

## 1. 这对「解锁被锁住的功能」意味着什么（目标②的性质重定义）

原先的表述是「E-P5 把 6 个录像艺术滤镜藏起来了」。
本轮证据要求改成：

> **「把 E-P5 的录像艺术滤镜菜单从 4 项改成 10 项」** ——
> 而这**不是恢复原厂功能，而是把 E-P5 改成别的机型的配置**。

### 有利条件（三条，都已验证）

1. **E-P5 的块 1 里那 10 个名字的字符串已经全在**（照片段 `A03F`–`A048`），
   连多语言版本都在 ⇒ **不需要新增任何字符串资源**。
2. **其他机型的块 1 里，录像菜单与照片菜单用的是同 10 个名字、不同的 ID 段**
   （例：E-M1 II v3.0 照片 `A032`–`A03B`、录像 `A073`–`A07C`）
   ⇒ **UI 框架本身支持"两张清单用同一批名字、不同 ID 段"**。
3. 第十四轮已定位**单字节补丁点**：`FUN_405731F7`（`rt 0x405731F7`）里
   `*(u8*)(state + 0x6B) = 4;` —— 9 个写入点中**只有它**会选到另一张 mask ROM 描述符。

### 不利条件（两条，决定成败）

1. **菜单项清单在 mask ROM**（第十八轮已证）⇒ 若 E-P5 的 ROM 里那张描述符只列了 4 个资源 ID，
   改类型码也换不出 10 项。**这一条只有 mask ROM dump 能判定。**
2. **mask ROM 地址区间逐平台不同**：
   E-P5 = `0x7Exxxxxx`（32,942 处引用），E-M1 II = `0x6Exxxxxx`（34,827 处），
   E-M1 II 的 `0x60/0x61/0x62` 分别是 34,827 / 12,680 / 4,432 处。
   ⇒ **不能拿别的机型的 ROM 描述符地址来做"10 项档是否存在"的判据**，
   必须在 E-P5 自己的地址空间里做。

### 由此得到的**可证伪判据**（下一步）

设 E-P5 的 `FUN_403E7E94` 返回的两张描述符为：

| 规范码 | 描述符地址 | 假设 |
|---|---|---|
| 0 / 1 | `0x7E452BDC` | 照片 10 项？ |
| 2 / 3 | `0x7E452BE4` | 录像 4 项？ |

**判据 A**：若 `0x7E452BDC` 里的 ID 列表是 `A03F`–`A048`（10 项）、
`0x7E452BE4` 里是 `A042`–`A045`（4 项），
则「把录像的类型码从 2 改成 0」即可让录像菜单读**同一张 10 项的清单** ——
**这时 1 字节补丁成立**（不需要改 ROM）。

**判据 B**：若两张描述符里的 ID 列表**各自独立**（一张 10 项、一张 4 项），
则 ROM 里**没有**「10 项的录像清单」可借，
只能靠"让录像菜单改引用照片那 10 个 ID"——这需要 ROM 侧的清单可写 ⇒ 需要 mask ROM 写权限。

⇒ **无论 A 还是 B，答案都在 mask ROM 的那两张描述符里。**
⇒ 这把「需要 mask ROM」的必要性**收窄到了两个具体的 4 字节地址**：
`0x7E452BDC` 与 `0x7E452BE4`（每个描述符 4 字节指针 + 其后的 ID 列表）。

---

## 2. 附带发现

### 2.1 同一个 `@Axxx@` 标记在不同机型上指向不同名字

| ID | E-P5 v1.8 | E-M10 II v1.4 |
|---|---|---|
| `A041` | Soft Focus | Monotone |
| `A042` | Pale&Light Color / Grainy Film | Grainy Film |
| `A043` | Light Tone / Pin Hole | Pin Hole |
| `A044` | Diorama / Grainy Film | Diorama |
| `A045` | Dramatic Tone / Pin Hole | Dramatic Tone |

⇒ **`@Axxx@` 不是全局唯一的字符串资源 ID**（同一 ID 在 E-P5 里甚至同时对应两个名字），
更像是**每张屏幕 / 每个语言分区各自编号**。
⇒ 任何"资源 ID 全局表"的假设都要推翻；**这也是为什么 E-P5 的照片段与录像段 ID 会重叠**
（`A042`–`A045` 同时出现在两段里）。

### 2.2 基础色彩模式（Vivid / Natural / Portrait / Muted / i-Enhance / Monotone）的 ID 也在动

E-P5 `A07A`–`A07C` / `A087`–`A089`；E-M10 II `A07A`–`A07C` / `A094`–`A096`；
E-M1 II `A073`–`A07C` 段还混着 `A0B3`–`A0B5`。
⇒ **同一家族内部，不同机型的 ID 段也不同**（E-M1 II 的 `A07A` 既是 Cross Process 又是 Vivid）。

---

## 3. 复现

```sh
python tools/cross_model_art_menu_ids.py \
    --blk1 "E-P5v1.8=<块1路径>" "E-M10IIv1.4=<块1路径>" ... \
    --json evidence/art_filter/cross_model_art_menu_ids.json

# 单机型的分区级明细（哪一段是照片菜单、哪一段是录像菜单）
python tools/block1_art_menu_survey.py --models "E-M10IIv1.4=<块1路径>"
```
