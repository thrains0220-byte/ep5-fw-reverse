# E-P5 1.8 艺术（创意）滤镜 —— 完整实现清单

> 日期：2026-10-22（第十轮）
> 目标：**把固件里实际存在的艺术效果全部枚举出来**，作为后续开发的参考基线。
> 方法：块 0 的 `art_*` 符号名聚类（752 条）＋ Ghidra 伪代码（艺术簇 83 个函数）。
> 性质：静态观察。

---

## 0. 最重要的结论

**E-P5 1.8 固件实现了 15 个艺术效果，而机身菜单只暴露了其中一部分。**
这意味着"新增创意滤镜"**不需要写新的图像处理算法**，
只需要把**已经存在的实现**挂到菜单上。

---

## 1. 全部艺术效果实现（15 个）

| # | 实现名 | pass 数 | `get_inf` | `free` | 编号 | 首现偏移 |
|---|---|---|---|---|---|---|
| 1 | `art_star_light` | 15 | ✅ | — | **ID 10** | `0x454F0D` |
| 2 | `art_artclearline` | 13 | ✅ | ✅ | **NN 19** | `0x457FBF` |
| 3 | `art_filter_dramatic_tone` | 12 | — | ✅ | **NN 14** | `0x457738` |
| 4 | `art_pastel_art` | 11 | — | ✅ | **NN 21** | `0x458AAD` |
| 5 | `art_diorama` | 9 | — | — | **NN 9** | `0x456EF6` |
| 6 | `art_filter_rough_monochrome` | 9 | — | — | **NN 6** | `0x4567B3` |
| 7 | `art_stl2ycc` | 7 | — | ✅ | — | `0x45A8A8` |
| 8 | `art_soft_focus` | 6 | — | — | **ID 40** | `0x455F35` |
| 9 | `art_frame` | 5 | — | ✅ | **ID 30** | `0x45589C` |
| 10 | `art_pinhole` | 5 | — | — | **ID 20** | `0x4555C6` |
| 11 | `art_white_edge` | 5 | — | — | **ID 50** | `0x456311` |
| 12 | `art_composite` | 4 | — | — | — | `0x458794` |
| 13 | `art_filter_gentle_sepia` | 3 | — | — | — | `0x4573BB` |
| 14 | `art_stl2ycc2` | 3 | — | — | — | `0x45A948` |
| 15 | `art_mirror` | 2 | — | — | — | `0x458611` |

### 两套编号体系

| 体系 | 取值 | 含义 |
|---|---|---|
| `art_effect_<ID>_<name>` | 10 / 20 / 30 / 40 / 50 | ID = 10 × 槽位号（槽位 1..5） |
| `art_filter_<NN>_<name>` | 06 / 09 / 14 / 19 / 21 | 另一套 2 位编号 |

两套**互不重叠**，合起来覆盖 10 个有名字的效果；其余 5 个（`art_stl2ycc`、
`art_stl2ycc2`、`art_composite`、`art_mirror`、`art_filter_gentle_sepia`）只有
实现名没有编号。

> `art_stl2ycc` / `art_stl2ycc2` 是**内部色彩空间转换**（STL→YCC），
> 不是用户可选的滤镜；`art_composite`、`art_mirror` 疑为内部合成/镜像处理。
> ⇒ **用户可选的候选艺术效果约为 10 个**。

### 与机身菜单名字的对应

块 1 里 E-P5 照片模式的名字（资源 ID A03F–A048）：

| 资源 ID | 名字 | 对应实现 |
|---|---|---|
| A03F | Pop Art | `art_pastel_art`? / `art_composite`? |
| A040 | Dramatic Tone | `art_filter_dramatic_tone` ✅ |
| A041 | Soft Focus | `art_soft_focus` ✅ |
| A042 | Pale&Light Color | `art_stl2ycc`? （色调映射）|
| A043 | Light Tone | — |
| A044 | Grainy Film | `art_filter_rough_monochrome` ✅ |
| A045 | Pin Hole | `art_pinhole` ✅ |
| A046 | Diorama | `art_diorama` ✅ |
| A047 | Cross Process | `art_mirror` / `art_composite`? |
| A048 | Gentle Sepia | `art_filter_gentle_sepia` ✅ |

**⇒ 明确"已实现但未在照片模式菜单出现"的：**
- `art_artclearline`（NN 19，13 个 pass）—— **Clear Line / 净化直线**
- `art_star_light`（ID 10，15 个 pass）—— **星光**
- `art_pastel_art`（NN 21，11 个 pass）—— **粉彩**

这三个都是**完整的 pass 管线**（10+ 个 pass），不是占位实现。

---

## 2. 艺术簇代码（`0x40788300–0x40789600`，83 个函数）

### 2.1 关键全局与函数

| 语义 | 地址 / 函数 |
|---|---|
| 效果 ID 全局 | `0x605FCD3C` |
| 效果类型全局 | `0x605FCD40` |
| 支持的类型位掩码 | `0x602AEB94` |
| 效果回调指针 | `0x602AEB54` |
| 效果参数区（当前生效） | `0x605FCD44`（312 B） |
| 效果 50 参数模板 | `0x605FCE7C`（312 B） |
| 拍照参数区 | `0x605FCA00` |
| 录像参数区 | `0x605FCCC4` |
| 效果 ID 设置器 / 复位器 | `FUN_407887E0` / `FUN_40789519` |
| 子系统总初始化 | `FUN_407883DD` |
| 按类型初始化 | `FUN_40788616`（通用）/ `FUN_4078866A`（star_light 专用） |
| 效果回调派发 | `FUN_40788CAC` |

### 2.2 模式分派器 `FUN_40788978`（伪代码，完整）

```c
void FUN_40788978(int param_1) {
  int *piVar1 = (int *)(param_1 + 8);
  int iVar3 = *(int *)*piVar1;

  if (iVar3 == 1) {                       /* 模式 1：初始化 + 0x31/0x43 派发 */
      FUN_40788cac(0x43);
      FUN_407bc720(*piVar1 + 8, 0, 8);
      FUN_407bc720(0x605fcfcc, 0, 0x9c);
      ...
      FUN_40788cac(0x31);
      FUN_407866a5(0x22);
      return;
  }
  if (iVar3 == -0x80000000) {              /* 模式 0x80000000：另一套状态结构 */
      uRam602aeb44 = uRam605fc9e8;
      iRam602aea1c = iVar3;
      FUN_40786a8e();
      return;
  }
  FUN_40786704(0x605fca00, *(undefined1 *)(param_1 + 5));   /* 默认：只绑定拍照参数区 */
}
```

### 2.3 录像/照片判定 `FUN_40788A6C`（伪代码，完整）

```c
void FUN_40788a6c(short *param_1) {
  if (**(int **)(param_1 + 4) == 0x20000000) {   /* ① 0x20000000 标志 */
      if (*param_1 == 0)      { uRam605fcfb8 = *(u8 *)(param_1 + 5); uVar1 = 0x11; }
      else if (*param_1 == 3) { uVar1 = 0x12; }
      else return;
  } else {
      if (**(int **)(param_1 + 4) != 1) return;   /* ② 模式 1 */
      uRam605fd064 = uRam602aeb6c;
      FUN_4078849b(0, 0, 0);
      FUN_40788cac(0x33);
      uVar1 = 0x22;
  }
  FUN_40788cac(uVar1);
}
```

**⇒ 三个模式标志已识别**：`0x20000000`（疑似录像）、`1`（照片）、`0x80000000`（第三类）。
`0x11/0x12/0x22/0x31/0x33/0x41/0x42/0x43` 是传给回调 `FUN_40788CAC` 的**子命令码**。

---

## 3. 仍需完成（"完全破解"的剩余部分）

| # | 缺口 | 手段 |
|---|---|---|
| 1 | **效果 ID → 实现函数**的注册表（15 个实现如何被选中） | 在 83 个函数里找对效果 ID 的分派；比较可能是 `ID/10` 索引表 |
| 2 | **菜单资源 ID → 效果 ID** 的对应表 | 块 1 菜单定义表（`@A0xx@` 前缀）+ 块 0 的 UI 资源 ID 索引表 |
| 3 | 每个效果的**参数区地址**（`art_get_dramatic_tone_addr` 说明有专门查询函数） | 逐个反编译 `art_<name>_get_inf` |
| 4 | 各效果**是否已在菜单暴露**的判定 | 比较块 1 菜单列表与实现清单 |
| 5 | `art_stl2ycc` / `art_composite` / `art_mirror` 是否为用户可选 | 查其 `get_inf` / 菜单引用 |
| 6 | 块 1 的完整结构（语言分区、字体、资源表） | 结构化解析 |
| 7 | 块 2 的 6-bit 编码 | 仍未解（四个独立项目未解） |
| 8 | 块 3 的 1bpp 位图格式 | 部分已知 |

---

## 4. 复现

```sh
# 全部艺术效果实现清单
python tools/art_effects_numbered.py

# 全部 art_* 符号按效果归组
python tools/art_effects_full.py

# 子系统测绘（日志标签 / g_* 全局 / 函数名簇）
python tools/subsystem_map.py decoded/strings.jsonl docs/subsystem_map.md

# 艺术簇全量反编译（需先播种函数）
#   tools/ghidra/seed.bat mn103_full 00_0100_402c0020.decoded.bin seeded.txt
#   tools/ghidra/decomp_range.bat mn103_full 00_0100_402c0020.decoded.bin artrange2.txt 0x40788300 0x40789600
```
