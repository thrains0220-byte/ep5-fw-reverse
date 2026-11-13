# E-P5 1.8：无暗角胶片色载体调查（针孔之外）

本页回答用户转向："针孔自带暗角，能不能找无暗角的纯色彩 ART 滤镜挂知名胶片色"。
全部为只读调查（原厂解码 MAIN，SHA `dfe255e4…c590df`），未生成固件、未访问相机。
调查脚本见 `build/_candidate_tables.py`、`_effect_entry.py`、`_effect_subtables.py`、
`_gentle_chroma.py`、`_gentle_slot_structure.py`。

## 决定性事实：原厂色度表全部恒等

直接读 98 字节表对（x[16]+y[16]+slope[17]，两轴）：

| 槽 | 表对地址 | 两轴内容 |
| --- | --- | --- |
| 针孔 I（73/82） | `0x7e438bb0` | 恒等 |
| 浓郁色调 gentle_sepia（91/93） | `0x7e438cd6` | 恒等 |
| 中性模式 69 | `0x7e438a28` | 恒等 |

**所有 ART 滤镜的原生色度曲线都是恒等。** 暗角、sepia 染色、模糊、颗粒等全部来自
效果函数（公共引擎按效果类型 ID 处理），色度表本身不做任何色彩。
（早期 `_candidate_tables.py` 报 gentle_sepia "非恒等" 是偏移布局误读，已用直接读表纠正。）

推论：
- 色度曲线补丁（RC2/三槽机制）对任何独立组槽都能注入饱和/偏移/去色。
- 但效果函数的空间/染色处理会**叠加**在色度曲线结果上，色度曲线**去不掉暗角**。

## 效果函数结构（入口反汇编）

每个效果函数入口结构一致：MOV 效果类型 ID → 引用日志字符串 → 调用公共引擎，分 3 pass。

| 滤镜 | 入口 | 效果类型 ID | 空间/染色性质 |
| --- | --- | --- | --- |
| 针孔 pinhole | `0x7e40115c` | 9 | 暗角（空间） |
| 浓郁色调 gentle_sepia | `0x7e4052e2` | 16 (0x10) | sepia 暖褐染色 |
| 戏剧色调 dramatic_tone | `0x7e4055ba` | 17 (0x11) | 局部对比（恒等色度组） |
| 清晰线条 artclearline | `0x7e4067dd` | 18 (0x12) | 线条增强（恒等色度组） |
| 柔和怀旧 pastel_art | `0x7e4085ef` | 21 (0x15) | 柔化染色（恒等色度组） |

入口引用的"子表"（如 gentle_sepia `0x7e558460`）只是 pass1/2/3 日志字符串，不是色彩参数。
真正的染色/空间参数在公共引擎内部，按效果类型 ID 分派。

## 色度组分类（决定能否补丁）

色度写入器把 256 个模式分成：

- **独立色度表组**（可像针孔一样补丁，6 指针表对）：
  69/78、70/79、71/80、72/81、73/82(针孔I)、85/87、86/88(diorama)、
  **91/93(gentle_sepia)**、102/103、106/107(针孔II)、108/109(针孔III)、
  118/122(star_light)、119/123、145/146、153/154(composite)、167/168。
- **大共享恒等组**（pair_rom=None，色度补丁无效，色彩全在效果函数内）：
  rough_mono(74/104)、dramatic_tone(96/165)、pastel(181/182)、artclearline(163/169) 等。

独立组里**无暗角/无模糊的纯色调载体只有 gentle_sepia(91)**；其余独立组都带空间效果
（diorama 上下模糊、star_light 星芒、mirror 镜像、composite 合成）。

## gentle_sepia 槽与针孔完全对称（可复用三槽机制）

| 项 | 针孔 I | gentle_sepia |
| --- | --- | --- |
| photo / shared 模式 | 73 / 82 | 91 / 93 |
| 共享 case_pc | `0x7e22a12f` | `0x7e22a1fb`（91/93 共享） |
| 表对基址 | `0x7e438bb0` | `0x7e438cd6` |
| 6 指针 deltas | 0,16,32,49,65,81 | 0,16,32,49,65,81 |
| CMIO 字面引用 | `0x7e21d0d1/0e7/0fd/113/129/13f` | `0x7e21d25d/273/289/29f/2b5/2cb` |

结论：三槽隔离机制（改 photo 曲线 + 共享 mode 重路由中性 case + CMIO 重定向）
可原样套用到 gentle_sepia。**但 gentle_sepia 仍排入 sepia 效果函数**，输出会带 sepia 暖褐底色：
- 适合暖调胶片（Gold 200 / Portra）——sepia 底色与暖调取向一致。
- 不适合冷调/高饱和（Velvia / Classic Chrome / Ektar）——sepia 底色会脏。

## 两条路线与风险

### 路线 A：gentle_sepia 单槽（低风险，复用已验证机制）
把浓郁色调槽挂一个暖调胶片色。机制与三槽相同，只需换槽地址。
**局限**：只有一个无暗角槽；带 sepia 底色；只适合暖调。需探针校验 91/93 隔离后方可刷。

### 路线 B：中性化多槽（彻底无暗角，需新集成验证）
让 ART 槽只排 RAW→YC（不排空间效果）+ 自定义色度曲线。
原厂列表构造已证明：packet `+6=0`、附加效果清零 → 只排 `0x7e40cbb1`(RAW→YC)
（见 NATIVE_CONTRACTS.md，`art_set_filter 0x7e40b368` 探针）。
**难点**：`+6=0` 时色度选择器走默认 RAM 分支（`CHROMA_DEFAULT 0x602aad9c`），
不命中 ROM 自定义曲线表。要"无空间效果 + 自定义色度"共存，需改列表构造或 packet 构造，
使色度命中自定义表而效果列表不排空间函数。完整任务调度/ISP/像素契约/取消/录像未验证。
这是 EP5_LUT_DELIVERY_PLAN 的核心难点，也是色度曲线路线一直无法去掉暗角的根因。

#### 默认分支取表机制（已静态追踪，只读）

色度选择器范围检查在 `0x7e229ff0`：mode 必须在 `0x45..0xa8`（69..168）才查 ROM 跳转表
`0x7e478e90`。中性 packet `+6=0` → mode 0 → 落默认分支。

默认分支在 `0x7e22a4f0`：`MOV A1, 0x602aad9c`，随后从该 **RAM** 地址读 6 个表指针
（`0x602aad9c` 全固件仅此处引用）。RAM 未初始化时后备到 ROM 记录 `0x7e478148`
（`0x7e22dd0f` 处 `MOV 0x7e478148`）。即默认表是**驱动参数 RAM 运行时填充**，不是 ROM 固定值。

推论：要让中性槽命中自定义曲线，只有两条路，都需**新增可执行代码或改固件逻辑**：
1. 运行时写 RAM `0x602aad9c` 的 6 指针（cave 代码 + 完整生命周期/取消/录像验证）。
2. 改效果分派表，让某个非零 mode 命中自定义 ROM 色度表但列表不排空间函数。

两者风险都远高于色度曲线补丁（后者只改 ROM 数据表、无新代码），且尚无真机验证。
调查脚本：`build/_chroma_default.py`、`_chroma_default_trace.py`、`_chroma_default_code.py`。

## 突破：效果函数中性化（纯数据补丁，已探针验证）

**关键发现**：`art_set_filter` 里的效果函数指针是 MOV 立即数（ROM 常量），不是运行时 RAM。
把该常量从效果函数地址改成 0，列表构造器就**只排 RAW→YC**，不排任何空间/染色效果。
同时 **packet mode 不变**（仍为 73/106/108），色度选择器仍命中自定义 ROM 曲线表。

这意味着：**只需改 4 字节 ROM 常量（×2 处），就能去掉针孔暗角，得到干净胶片色槽。**
不需要新增代码、不需要 cave、不需要控制 RAM。风险与色度曲线补丁相同（纯数据）。

CPU 探针证明（`build/_neutralize_probe.py`、`_neutralize_pinhole.py`）：
- 清零 gentle_sepia 指针 → REC 108 只排 RAW→YC，mode 91 不变。
- 清零 pinhole 两处指针 → REC 105 三个变体只排 RAW→YC，mode 73/106/108 不变。
- 其他所有滤镜（REC 101/104/106/108/109/115/119/120）完全不受影响。

### 中性化三槽交付物（已验证，可刷）

`tools/build_neutral_trio.py` + `tools/build_neutral_trio_kit.py`：
在已验证三槽机制基础上，额外清零 pinhole 效果指针（`0x7e40b639`、`0x7e40b87a`）。

| 组合 | 针孔 I | 针孔 II | 针孔 III | 校验 |
| --- | --- | --- | --- | --- |
| A | Velvia 50 浓艳 | Classic Chrome 纪实 | Gold 200 暖负片 | 写入器+路由 9 组全 PASS |
| B | Portra 160 人像 | Velvia 50 浓艳 | 森山黑白 | 写入器+路由 9 组全 PASS |

交付物：
- `build/ep5-neutral-trio-kit/`（组合 A + 官方恢复包）
- `build/ep5-neutral-trio-kit-b/`（组合 B + 官方恢复包）

校验脚本：`tools/film_pack/verify_neutral_trio.py`、`verify_neutral_trio_route.py`、
`verify_neutral_trio_b.py`。回归 23 项全过。

**与 Canon M-Film / Soup Engine 的对比**：
- 它们通过 Magic Lantern 加载额外 C 代码做机内显影（33³ LUT + 四面体插值）。
- 我们通过中性化 + 原生色度曲线，在 ISP 全幅显影后、JPEG 编码前注入色彩。
- 共同点：RAW 不动、全幅一次压缩、卡上可换风格（下一步 SD LUT）。
- 差异：色度曲线只能做饱和/偏色/去色，不能做任意 3D LUT（色相旋转/亮度曲线）。
  任意 .cube 仍需 SD LUT 运行时主线（cave 代码）。

**状态**：hardware-functional-candidate。机制与隔离经探针证明，**未在相机实拍**。
刷入后预期：ART → 针孔相机 → 右键 I/II/III，无暗角、无模糊、无 sepia，
只有胶片色彩取向。取景预览可能仍显示原厂针孔效果（预览路径未验证），
最终 JPEG 以色度曲线为准。

## 给用户的诚实结论

- 色度曲线机制能注入胶片取向（饱和/微偏色/去色），但**不能去暗角、不能色相旋转、不能亮度 S 曲线**。
- 现成无暗角载体只有浓郁色调（带 sepia 底色，适合暖调）。
- 要"多个干净无暗角胶片槽 + 任意 .cube"，必须走中性化集成或 SD LUT 运行时主线，
  两者都需新的真机验证，不能沿用针孔三槽的成功结论。

## 已交付：浓郁色调无暗角胶片包（路线 A，已探针验证）

`tools/build_gentle_film.py` 把 RC2 色度曲线机制挂到浓郁色调槽（photo 91 / shared 93）。
`tools/build_gentle_film_kit.py` 打成可刷 ZIP（含官方恢复包），逐包回读校验。

已构建并通过两项原生探针校验的风格：

| 风格 | 固件 SHA-256 | 写入器校验 | 拍摄路径校验 |
| --- | --- | --- | --- |
| gold200 柯达金200 | `b661920349a7c0c9…1fd19a` | PASS（仅 91 变，93 及其余原厂） | PASS（ms7/8/9，全幅 4608×3456） |
| portra160 人像160 | `115b2050183dc1a8…bc515d` | PASS | PASS |

校验脚本：`tools/film_pack/verify_gentle.py`（写入器隔离）、
`tools/film_pack/verify_gentle_route.py`（完整拍摄路径，REC 108→mode 91，
filter `0x7e4052e2`，converter `0x7e40cbb1`，全幅分配 31,850,496 字节）。
路由探针 `tools/ep5_gentle_route_probe.c` 由 `ep5_film_route_probe.c` 改 REC 105→108 生成。

交付物：`build/ep5-gentle-kit/`（gold200、portra160 各一 ZIP + 官方恢复包）。
回归：`tests.test_native_film_pack / test_build_native_film / test_film_update` 23 项全过。

**状态**：hardware-functional-candidate。机制与隔离经探针证明，但**未在相机实拍**；
sepia 底色与最终 JPEG 色彩需上机对照。一次只刷一个风格（都占浓郁色调槽）。

### 复现

```bash
# 构建单风格（新本地目录）
python tools/build_gentle_film.py data/ep5-stock/OLY_E_108_1800_0000_0000.BIN \
  --look gold200 --label-zh 柯达金200 --label-zht 柯達金200 --out build/film-gentle-gold200
# WSL：两项探针校验
PYTHONPATH=. python3 tools/film_pack/verify_gentle.py gold200
PYTHONPATH=. python3 tools/film_pack/verify_gentle_route.py gold200
# 打 kit（含恢复包）
python tools/build_gentle_film_kit.py data/ep5-stock/OLY_E_108_1800_0000_0000.BIN --out build/ep5-gentle-kit
```
