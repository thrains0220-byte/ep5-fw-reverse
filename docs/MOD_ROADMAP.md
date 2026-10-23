# E-P5 固件魔改实现路线图（目标导向）

> 目标：**在不变砖的前提下，在固件层面实现「新增创意滤镜 / LUT 直出 / 解锁计算摄影功能 / 其它有趣功能」**。
> 判定标准：每一个改造都必须能落到**具体字节或具体 ROM 地址 + 可验证的行为变化**。
>
> 相关：[`HARDWARE_RUNBOOK.md`](HARDWARE_RUNBOOK.md)（实机操作）、
> [`PROJECT_STATUS.md`](../PROJECT_STATUS.md)（事实总表）、
> [`../evidence/unlock/community_patch_A_semantics.md`](../evidence/unlock/community_patch_A_semantics.md)（社区补丁先例）

---

## 0. 三个层次的架构事实（决定了一切方案）

```
① 机身 mask ROM  0x7E000000–0x7EFFFFFF     图像引擎：滤镜算法 art_*、参数块、类型白名单
      ▲ 引用（块 0 里 32,942 次 0x7Exxxxxx 立即数）
② 主控固件块 0  0x402C0000  (15.7 MB MN10300)  菜单/UI/模式管理/参数搬运/调度
      ▲ 装载
③ 块 3 (kind 0x104) 0x44000000 (3.67 MB, 8 段压缩)  另一模块区
```

【观察】块 0 的模块装载器 `FUN_4050919b` 列出全部可映射模块基址：

```
0x411C0000  0x427C0000(块1)  0x43DA0000(块2)  0x44000000(块3)
0x44380000  0x45780000  0x45A00000
```

⇒ **`0x7E000000` 不在其中** ⇒ mask ROM 是独立分区，**不可通过固件更新替换**。

---

## 1. ★ ROM 侧艺术效果清单（本轮新发现）

【观察】块 0 字符串池里有 **752 个 `art_*` 名字**（带 `in`/`out` 标记与 `.c` 源文件名），
这是**随主控固件下发的 ROM 侧图像引擎函数名表**。由此得到 ROM 里实现的滤镜效果：

| ROM ID | 名字 | 典型子函数 | E-P5 菜单 |
|---|---|---|---|
| `0x10` | `art_effect_10_star_light` | pass1…pass15 + `get_inf` | ❌ **隐藏** |
| `0x20` | `art_effect_20_pinhole` | pass1…pass5 + `set_gainmap` | ✅ Pin Hole |
| `0x30` | `art_effect_30_frame` | `check_param` `get_res_ID` `get_jpeg_revision` | ❌ **隐藏** |
| `0x40` | `art_effect_40_soft_focus` | pass1…pass6 + `set_reduce` | ✅ Soft Focus |
| `0x50` | `art_effect_50_white_edge` | pass1…pass5 | ❌ **隐藏** |
| `0x06` | `art_filter_06_rough_monochrome` | pass1…pass9 + `skip_all_check` `mov_check` | ✅ Grainy Film |
| `0x09` | `art_filter_09_diorama` | pass1…pass9 + `set_gainmap` | ✅ Diorama |
| `0x0E` | `art_filter_0e_gentle_sepia` | pass1…pass3 | ✅ Gentle Sepia |
| `0x14` | `art_filter_14_dramatic_tone` | pass1…pass12 + `skip_all_check` | ✅ Dramatic Tone |
| `0x19` | `art_filter_19_artclearline` | `artclearline_get_inf` | ❌ **隐藏** |
| `0x1C` | `art_filter_1c_mirror` | pass1…pass2 | ✅ Cross Process |
| `0x1D` | `art_filter_1d_composite` | pass1…pass4 + `set_CompositeData` | ✅ Pop Art |
| `0x21` | `art_filter_21_pastel_art` | pass1…pass11 + `free` | ❌ **隐藏** |
| — | `art_stl2ycc` / `art_stl2ycc2` | pass1…pass7 + `free_yc` + `buffer_check` | ✅ Pale&Light / Light Tone |

⇒ **ROM 里实现了 15 个具 ID 的效果 + 2 个 stl2ycc，E-P5 菜单只暴露 10 个。**
⇒ **5 个 ROM 已实现但 E-P5 菜单未暴露**：`star_light` `frame` `white_edge` `artclearline` `pastel_art`。
（`pastel_art` 是 **2016 年后机型才上市**的效果 —— E-P5（2013）的 ROM 里居然有它。）

【观察】ROM 侧还有整套调度/判定接口：
`art_main_init` `art_get_filterlist_tbl` `art_set_func_effect` `art_init_filter_proc`
`art_get_tsk_tbl` `art_get_msg` `art_send_msg` `art_chk_type` `art_chk_type_rec` `art_chk_type_mov`
`art_mov_check` `art_mov_check_thr` `art_chk_effect` `art_chk_submode` `art_chk_proccont`
`art_get_dramatic_tone_addr` `art_get_ldata_size`

⇒ **「滤镜链表」在 ROM 侧**（`art_get_filterlist_tbl`），主控通过消息机制请求执行。
⇒ **`art_chk_type_rec` / `art_chk_type_mov` / `art_mov_check` 是 ROM 侧「录像形态白名单」**，
主控侧那个 `0x602AEB94` 位掩码只是粗筛。

> 清单落盘：[`../evidence/art_filter/rom_art_api.json`](../evidence/art_filter/rom_art_api.json)
> 生成工具：`tools/art_api_inventory.py`

---

## 2. 六条改造路线

### R-1 ★ 隐藏滤镜解锁（5 个）

| 项 | 内容 |
|---|---|
| **目标** | 让 E-P5 菜单出现 `star_light` `frame` `white_edge` `artclearline` `pastel_art` |
| **落点 1** | 菜单描述符：**ROM** `0x7E452B30–0x7E452BFC` 族里的某几项（每项 4 B）—— 需 ROM dump 才知道哪项对应哪个效果 |
| **落点 2** | 20 槽参数块表：**块 0** `0x40A56338`（20 × 4 B）—— 可改，把录像/新增槽指向对应 ROM 参数块 |
| **落点 3** | 效果 ID 分派：**块 0** `FUN_4078846D` / `FUN_4078849B` / `FUN_40788562`（`0x605FCD3C` 效果 ID 的设置路径） |
| **改动量** | 块 0 侧 ≤ 20 B；ROM 侧若可写则需改 4 B/项 |
| **风险** | 菜单项数由 ROM 描述符决定 ⇒ **若 ROM 描述符写死 10 项，块 0 改不动** ⇒ 依赖 ROM dump |
| **验收** | 菜单出现新项；拍照出图风格正确；录像形态同样可用 |

### R-2 ★ 录像形态解锁（照片 10 项 → 录像 10 项）

| 项 | 内容 |
|---|---|
| **目标** | 录像模式下也能选全部 10 个照片艺术滤镜 |
| **落点 1** | 菜单类型码：**块 0** `FUN_405731F7` 末尾 `*(u8*)(state+0x6B) = 4` → 改 `= 0`（1 字节） |
| **落点 2** | 类型白名单：**块 0** `0x602AEB94` 位掩码（置上录像侧位） |
| **落点 3** | 效果初始化：只调 `FUN_4078866A(2)`（拍照）不调 `(1)`（录像）的那些效果初始化函数 |
| **落点 4** | ROM 侧 `art_chk_type_rec` / `art_chk_type_mov` / `art_mov_check` —— **真正的细筛在 ROM** |
| **改动量** | 块 0 侧 1 B + 数个字节；ROM 侧未知 |
| **验收** | 录像模式下艺术滤镜菜单 10 项，逐项出图 |

### R-3 ✔ AF 驱动步数上限解除（**已完成配方**）

| 项 | 内容 |
|---|---|
| 落点 | 块 0 `0x4058A31F`（`MOV 0x6cc,A3`）、`0x4058A2DF`（`MOV 0x1c20,A3`） |
| 改动 | 6 字节：`27 cc 06`→`27 ff ff`、`27 20 1c`→`27 ff ff` |
| 效果 | AF 步数上限 1740/7200 → 65535；**只对 `step==3` 分支有实际增益**（+36%/+71%） |
| 状态 | ✅ 配方已做，`tools/make_patched_firmware.py` 对官方 v1.8 端到端验证通过 |
| 风险 | 低（等长覆盖 + 校验和重算；社区补丁同款手法） |

### R-4 ★★ ROM 可写性判定 → 自制 LUT 直出（**最高价值，也最关键**）

| 项 | 内容 |
|---|---|
| **想法** | 固件自带 `memload NAME ADR [LEN] - load memory from file` ⇒ 若 `0x7Exxxxxx` 运行时可写，就能把**自制的 LUT / 色调曲线**直接写进 ROM |
| **为什么可能可行** | 每个艺术效果的参数是 **u16 数组**（照片参数块 312 B；E-M10 II 的 `kind 0x106` 里还有 **10 条 41,472 B 的 u16 色调曲线**）；ROM 里还有 `art_get_dramatic_tone_addr` / `art_get_ldata_size` ⇒ **ROM 里有查表型(LUT-like)数据** |
| **判定实验** | 往一个**无害**的 ROM 地址写一个已知值 → `memdump` 回读比对 → 相同即证明可写 |
| **若可写** | 「森山大道风格」「LUT 直出」的实现方式 = ① 自制 u16 曲线/LUT ② `memload` 写进 ROM ③ 让某个效果的参数指针指向它（槽位表 `0x40A56338` 在块 0，可改） |
| **若不可写** | 退回「在块 0 的 RAM 参数区里改写变体」——变体数据必须来自 ROM 现有参数块 |
| **依赖** | 需要路线 A/B 提供的 ROM dump 与内存读写通道 |

### R-5 ★ 计算摄影限制常量分诊（**广撒网，纯固件层，不需 ROM**）

| 项 | 内容 |
|---|---|
| **原理** | 社区解锁补丁的本质 = 把「出厂限制常量」改大（AF 步数上限就是范例） |
| **已有清单** | `tools/ghidra/Mn103FindLimitCmp.java` 扫出 **89,295 个「CMP #立即数」** 点，分布在 22,471 个函数 |
| **下一步** | 按子系统收敛：连拍张数 / 最长快门 / ISO 上限 / 降噪帧数 / 景深合成张数 / 包围曝光 / 闪光同步 / 视频时长 |
| **产出** | 每条候选：函数地址 + 立即数 + 「它限制什么」+ 1–4 字节改法 + 风险 |
| **风险** | 低（等长覆盖）；但**改错会出怪现象** ⇒ 每条都要实机对照 |

### R-6 mask ROM 取数通道（**工具就绪，入口待定位**）

| 项 | 内容 |
|---|---|
| A | 进固件自带 `FileSystem Debug Command` → `memdump NAME ADR LEN`。**零变砖风险**。入口待定位（分派代码不在块 0 内） |
| B | 改固件插「开机把 `0x7E000000–0x7EFFFFFF` 写进 SD 卡」的代码 → 卡刷。工具（补丁工厂）已就绪，缺文件写 API 地址 |
| C | 拿到 dump 后 `tools/rom_fill_report.py` 一次读出 R1–R12 全部判据 |

---

## 3. 排序与依赖

```
R-6 (取 ROM)  ──┬──► R-1 (隐藏滤镜)      需要 ROM 菜单描述符
   (需实机)     ├──► R-2 (录像形态)      需要 ROM 侧 chk_type/mov_check
                └──► R-4 (LUT 直出)     需要 ROM 可写 + 参数块指针可控

R-3 (AF 步数)  独立，已可执行
R-5 (限制常量) 独立，纯固件层，可与上面并行
```

**优先级**：
1. **R-6**（解锁一切的前提）→ 用户手上就有实机，**最该先动**
2. **R-3**（已可执行，先验证「社区补丁手法」在 E-P5 上确实有效）
3. **R-5**（纯固件层广撒网，产出「计算摄影功能解锁」清单）
4. **R-1 / R-2**（依赖 ROM dump）
5. **R-4**（依赖 ROM 可写）

---

## 4. 不变砖的保证

| 原则 | 做法 |
|---|---|
| 只做**等长覆盖** | 补丁工厂强制 `len(find) == len(replace)`，不等长直接拒绝 |
| **命中数必须唯一** | 命中数 ≠ 1 直接拒绝生成（社区补丁只改 12 B / 2 B，也是等长） |
| **块校验和自动重算** | `oly_container.replace_payload()` 重算加性校验和；重打包后再解回自检 |
| **不碰头尾与元数据** | 只改 payload，块头/块尾/型号/版本字段不变 |
| **保留官方原版** | 任何时候可刷回官方 v1.8（奥记不检查降级） |
| **改过的固件不入库** | 改机固件著作权属 Olympus；本仓库只留**配方 + 工具**，让用户本地生成 |
| **分步验证** | 先刷官方 v1.8 确认卡刷通路，再刷补丁；每步都有验收判据 |

---

## 5. 本轮新增/修正的技术事实

| 项 | 内容 |
|---|---|
| **块 0 字符串的引用机制** | **不是**绝对地址立即数；而是「基址 + 索引」经查表助手取用 + **字符串驻留表按 hash 查**。⇒ 之前用 u32 搜字符串地址**全部归零是方法性错误**，第 20 轮「艺术滤镜串 0 引用」结论**不成立**（该结论已按 ROM API 清单方向修正） |
| ROM 侧 API 清单 | 752 条 `art_*`，含 15 个具 ID 效果 + 调度/判定接口 |
| 块 0 立即数分布 | 6.49 M 条指令里，落在块 0 自身地址范围内的标量只有 **144 个不同值**（全是页对齐 RAM 区基址） |
| 内存分区 | 块 0 的模块装载器列出 7 个模块基址；`0x7E000000` 不在其中 |
| 限制常量 | 89,295 个 `CMP #imm` 点 / 22,471 个函数（完整清单可导出） |

---

## 6. 实机需要用户配合的（已在 `HARDWARE_RUNBOOK.md` 展开）

1. 卡刷官方 v1.8（把相机对齐到分析版本）
2. 反馈 AF 灯表现与版本字符串
3. 反馈相机插 USB 到 PC 的设备模式（MTP / PTP / 串口）
4. （若愿意）试 `memload` 往一个无害 ROM 地址写 + 回读 —— 一次实验决定 R-4 是否成立
