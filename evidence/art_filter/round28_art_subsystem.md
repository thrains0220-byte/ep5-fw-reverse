# 第二十八轮：E-P5 艺术滤镜子系统解剖 + 三个可实机验证的补丁

> 证据分级：**观察** = 字节/反汇编可直接核对；**推断** = 由观察推导但未实机验证；**未知** = 目前无法确定。
> 全部地址基于 E-P5 v1.8 官方固件 `OLY_E_108_1800_0000_0000.BIN`
> （SHA-256 `cc59a4e13b3bf6c46405bd396975cb9c93a7634b7a4a36822259b1fc498b5cfd`）。
> 块 0 基址 `0x402C0000`，Ghidra 运行地址 = 块内文件偏移 + 块基址。

---

## 0. 本轮最重要的结论（一句话）

**艺术滤镜的「闸门」在块 0（可改），「数据与注册表」在 0x7E 区（不可改）。**
所以可做的改造是「**改闸门**」和「**改已有滤镜的实现**」，而不是「新增滤镜条目」。

并且：**第 20 / 25 轮「滤镜算法在 mask ROM、`.BIN` 里没有」这一结论是错的** —— 滤镜的
**像素级实现与 22 套曝光预设就在块 0 里**（见 §6）。错的只是「菜单清单/注册表」在 ROM。

---

## 1. 官方 v1.8 容器的真实结构（观察）

第 23 轮说的「50 映像 / 245 块」是跨机型汇总，**E-P5 v1.8 自己只有 4 个块**：

| 块 | kind | 容器地址 | 解码后大小 | 内容 |
|---|---|---|---|---|
| 0 | 0x0100 | 0x402C0000 | 15,728,576 | 主控代码 + 字符串 + 资源（`00_0100_402c0020.decoded.bin`） |
| 1 | 0x0101 | 0x427C0000 | 22,937,536 | 资源包：首部 70 条 (地址,长度) 目录；含 25 份语言包、若干参数块 |
| 2 | 0x0106 | 0x43DA0000 | 2,490,304 | 8 字节头 + 0x3E0 起的 **2,359,296 字节高熵载荷**（zlib/lzma/gzip 均解不开） |
| 3 | 0x0104 | 0x44000000 | 3,669,952 | 8 份 JPEG（首部 8 条目录） |

**0x7E 区不在 `.BIN` 里（观察）**：块 1–3 内所有「连续 ≥6 个 0x7Exxxxxx u32」的串都出现在
像素数据（`0x7f7f7f7f` 之类）或 JPEG 里，没有一处是指针表；而块 0 里有 1551 段这样的指针表。
⇒ `0x7E000000+` 是**另一侧存储/处理器的地址空间**，其内容不在升级包里。

---

## 2. 艺术滤镜子系统的地址地图（观察）

```
0x40714EF4  art_effect_10_star_light        ← 实现（字符串池里的 trace 标记）
0x407155B0  art_effect_20_pinhole
0x40715888  art_effect_30_frame
0x40715F1C  art_effect_40_soft_focus
0x407162F8  art_effect_50_white_edge
0x40716794  art_filter_06_rough_monochrome
0x40716EE0  art_filter_09_diorama
0x4071771C  art_filter_14_dramatic_tone
0x40717FA4  art_filter_19_artclearline
0x40718A94  art_filter_21_pastel_art

0x406B186F–0x406B1CFA  22 套 MODE_EXPOSE_* 曝光预设（每套都有 _MOVIE 版）

0x40788300–0x40789600  艺术簇（83 函数）：
  0x407883D4  FUN_407883D4   MOVHU D0,(0x602AEB94)      ← 类型支持掩码「取值器」
  0x407883DD  FUN_407883DD   初始化：效果ID==0 时 FUN_40788616(1)、FUN_40788616(2)、设默认效果
  0x4078846D  FUN_4078846D
  0x4078849B  FUN_4078849B   拷贝 0xB2(178) 个 dword 参数块
  0x40788562  FUN_40788562   应用滤镜
  0x40788616  FUN_40788616   ★ 闸门 A：mask & type → 0 则「不支持」
  0x4078866A  FUN_4078866A   ★ 闸门 B：同上
  0x407887E0  FUN_407887E0   效果 ID 取值 (0x605FCD3C)

0x403E7B1B / 0x403E7B79 / 0x403E7C3F   ★ ROM→CPU0 回调：「拍摄模式 → ROM 滤镜描述符」
0x403ED4B4  FUN_403ED4B4   类型码 → 拍摄模式(0..6) 映射（块 0 内有 32 个调用点）
```

关键 RAM 变量：

| 地址 | 含义 |
|---|---|
| `0x602AEB94` | 16 位「类型支持掩码」，**ROM 写、块 0 只读** |
| `0x602AEB96` | 1 字节「需重算」标志 |
| `0x605FCD3C` | 当前效果 ID |
| `0x605FCD44` | 滤镜参数结构（712 字节，从 `0x605FCE7C` 拷来） |
| `0x605FCA00` / `0x605FCCC4` | 拍照 / 录像 参数结构基址 |
| `0x7E5C9809` / `0x7E8973D0` | ROM 侧 拍照 / 录像 滤镜参数源 |

---

## 3. 滤镜初始化 / 应用流程（观察）

`FUN_40788616(t)`：

```
MOVHU (0x602AEB94),D1      ; D1 = ROM 给的类型支持掩码
AND  D0,D1                 ; D1 = 掩码 & 请求类型 t
BEQ  → 返回 0（该类型不支持）
CMP  0x2,D0
BNE  → 录像分支：FUN_407BC0BE(0x605FCCC4, 0x7E8973D0)
      拍照分支：FUN_407868FC(0x605FCA00, 0x7E5C9809)
```

`FUN_407883DD`（初始化，只在「当前效果 ID == 0」时跑）：
`FUN_40788616(1)` → 录像参数源；`FUN_40788616(2)` → 拍照参数源；随后设默认效果。

---

## 4. 闸门 A/B：`0x602AEB94` 类型支持掩码（观察）

**Ghidra 全局引用（`Mn103FindGlobalRefs`）结果：该地址在块 0 里只有 3 处引用，全部是读。**

| 地址 | 指令 | 作用 |
|---|---|---|
| `0x407883D4` | `MOVHU D0,(0x602AEB94)` | 取值器（块 0 内 0 个调用点 ⇒ 也是 ROM 回调） |
| `0x40788616` | `MOVHU (0x602AEB94),D1` | 闸门 A |
| `0x4078866A` | `MOVHU (0x602AEB94),D1` | 闸门 B |

⇒ **掩码由 ROM 侧下发**，块 0 只是照着执行。
⇒ 但**闸门本身在块 0**，可以绕过。

字节层面：

```
fc ad 94 eb 2a 60   =  MOVHU (0x602AEB94),D1   （fc ad = MOV #imm32,A13）
fc 83 94 eb 2a 60   =  MOVHU D0,(0x602AEB94)    （取值器，全块唯一）
```

`fc ad 94 eb 2a 60` 在块 0 中**恰好命中 2 处**（`0x40788616` 与 `0x4078866A`）。

---

## 5. ROM→CPU0 回调：「拍摄模式 → 滤镜描述符」（观察）

```
FUN_403E7B1B(A0=?)  D0 = 当前拍摄模式
    模式 0/1/3 → 0x7E452B30      模式 2 → 0x7E452B40
    模式 4 → 0x7E452B48          模式 5 → 0x7E452B50      模式 6 → 0x7E452B58

FUN_403E7B79(A2)   D0 = MOVBU (0x6B,A2)      ← ★ 第 27 轮 C1 改的就是这个字段
    D0 = FUN_403ED4B4(D0)
    模式 0/1/3 → 0x7E452B34      模式 2 → 0x7E452B44
    模式 4 → 0x7E452B4C          模式 5 → 0x7E452B54      模式 6 → 0x7E452B5C

FUN_403E7C3F(A2)   同样以 (0x6B,A2) 为键
    模式 1 → 0x7E452B64   模式 2 → 0x7E452B68   模式 4 → 0x7E452B6C
    模式 5 → 0x7E452B70   模式 6 → 0x7E452B74   默认 → 0x7E452B60
```

**这三个函数在块 0 里 0 个调用点**（用自建的 CALL 编码扫描器全块 133,044 个 `cd` 指令复核，
同一套规则能把 `FUN_403ED4B4` 找出 32 个调用点 ⇒ 方法有效）。
⇒ **它们是被 ROM 回调的 CPU0 服务函数**：滤镜清单由 ROM 决定。

### 5.1 类型码 → 拍摄模式（观察）

`FUN_403ED4B4(D0)`：

```
EXTBU D0 ; D1 = D0 & 7
  D1∈{2,3} → 模式1     D1∈{4,5} → 模式2     D1==7 → 模式3     D1==1 → 模式0
D1==0 时看高位：  0x20→模式1   0x80→模式4   0xA0→模式5   0xC0→模式6   其它→模式0
```

### 5.2 偏移 0x6B（类型码字段）的全部写入者（观察）

| 地址 | 写入值 | 对应模式 |
|---|---|---|
| `0x4056439D` | `0x78` | 模式 0 |
| `0x40573298` | `4` | 模式 2（**第 27 轮 C1 改的就是这里**） |
| `0x405B6D78` | `0xC0` | 模式 6 |
| `0x405B92DD` | `0xC0` | 模式 6 |

**推断**：模式 6（类型码 `0xC0`）＝照片 ART 模式；模式 2（类型码 `4`）＝电影艺术模式。
第 27 轮 C1 把 `4` 改成 `0`，等于把电影艺术模式改指到「模式 0」那一组描述符
（`0x7E452B30/34`、`0x7E452B60`）——**未必是照片 ART 那一组**，这解释了为什么 C1 期望不明确。

---

## 6. ★ 更正：滤镜实现与曝光预设在块 0 里（观察）

第 20/25 轮的结论「艺术滤镜算法在 mask ROM」**是方法性错误**。
块 0 的字符串池里直接躺着：

```
0x407155B0 'art_effect_20_pinhole'      + art_pinhole_pass1..5 / art_pinhole_set_gainmap
0x40716794 'art_filter_06_rough_monochrome' + art_filter_rough_monochrome_pass1..9
0x406B1B24 'MODE_EXPOSE_DRAWING'   / 'MODE_EXPOSE_DRAWING_MOVIE'
0x406B1CA8 'MODE_EXPOSE_PASTEL'    / 'MODE_EXPOSE_PASTEL_MOVIE'
0x406B1BE0 'MODE_EXPOSE_WATERCOLOR'/ 'MODE_EXPOSE_WATERCOLOR_MOVIE'
… 共 22 套
```

22 套预设名：composite / cross_process / cross_process_2 / crystal / daydream /
dramatic_tone / dramatic_tone_2 / drawing / fantastic_focus / fish_eye / gentle_sepia /
light_tone / ligne_clair / miniature / mirror / pastel / popart / rock / rough_monochrome /
tender_light / toy_photo / watercolor。

**这些名字在 E-P5 的 ART 菜单里一个都没有出现**（E-P5 只有 10 项）。
⇒ **滤波清单在 ROM，滤镜本体在块 0** —— 这正是「加不了新滤镜、但能改已有滤镜」的根因。

⇒ **「LUT 直出」的现实形态**：不能新增滤镜，但可以**改写块 0 里已有滤镜的像素处理/参数**，
例如把 `art_effect_30_frame`（暗角）改成自定义曲线。增益/色调曲线数据是否也在块 0，
**尚未确认**（下一步要定位 `art_*_set_gainmap` 实际读的表）。

---

## 7. 本轮补丁（等长覆盖，命中数已验证唯一）

| 配方 | 改动 | 字节 | 命中 | 期望效果 |
|---|---|---|---|---|
| `patches/ep5_art_typegate_pattern.json` | 解除类型支持掩码闸门 | `fcad94eb2a60` → `2dffffcbcbcb` | 2 | 不再受 ROM 下发的类型掩码限制 |
| `patches/ep5_art_moviemode_pattern.json` | 电影艺术模式(mode 2)描述符 → 照片 ART(mode 6)描述符 | `fcdc442b457e`→`fcdc5c2b457e`；`fcdc682b457e`→`fcdc742b457e` | 1+1 | 电影 ART 菜单用照片 ART 的滤镜清单 |
| `patches/ep5_art_typegate_moviemode.json` | 上面两条同时 | — | 2+1+1 | 两个闸门一起打开 |

编码依据（全部由 Ghidra 反汇编 + 字节比对确认）：
`fc dc`=MOV #imm32,A0；`fc ad`=MOV #imm32,A13；`2d XX XX`=MOV #imm16,D1；`cb`=NOP。

构建产物（自检：容器往返逐字节一致 + 重新解析 4 块校验和自洽）：

| 固件 | SHA-256 |
|---|---|
| `OLY_E_108_1800_0000_0000.TYPEGATE.BIN` | `538a3fefe952db27469b1b79fff93192da8d7c15ba08d436da1bcfdd65d10599` |
| `OLY_E_108_1800_0000_0000.MOVMODE.BIN` | `a5e021e5905c683debc341ca23ee51ff61d41d4612292be1164d5ee875d34207` |
| `OLY_E_108_1800_0000_0000.BOTH.BIN` | `723cffce2191eaa978bd0aeff5c31491862b47904ffe35227cf9c9787fcf6f10` |

SD 卡目录（与已验证配方一致）：`<目录>\DCOLYMP\E1089999.BIN`

---

## 8. 对第 27 轮 C2/C3 的更正（推断）

第 27 轮把块 0 偏移 `0x796338`（地址 `0x40A56338`）当作「20 槽滤镜参数块表」，
依据是那里有 20 个指向 `0x7E5C91xx` 的指针。
但本轮把 `0x40A56180–0x40A56420` 整段dump 出来后发现：同一区域里紧挨着
`x-bt/img-capabilities` / `x-bt/img-listing` / `x-bt/img-properties` / `x-bt/img-thm` /
`x-bt/img-monitoring` 等 **XMP/EXIF 命名空间属性名**，`BIPIND_IMAGE`、`TSK_BTIA` 等任务名。

⇒ 那张「20 槽表」**更可能属于 XMP/EXIF 描述符区**（把当前滤镜名写进图片元数据用），
而不是 ART 菜单数据。**C2/C3 的前提被证伪**，建议不要刷，或只当对照组刷一次。
（艺术滤镜真正的参数路径是 `0x605FCA00`/`0x605FCCC4` + ROM `0x7E5C9809`/`0x7E8973D0`，见 §2。）

---

## 9. 仍未解决（未知）

1. ROM 里 `0x7E452B30` 那张表的**实际内容**（哪个模式对应 10 项 / 4 项）—— 只能靠实机试验或拆机读 ROM。
2. ROM 是否能通过官方通道下发 —— 第 23 轮已穷尽官方通道，结论是不会。
3. `0x602AEB94` 由谁写 —— 块 0 无写入点，只能是 ROM 或 DMA。
4. 各滤镜的增益/色调曲线表在块 0 还是 ROM —— **决定「LUT 直出」是否可行**，下一步就查这个。
5. 调试 shell（`dump` / `oly fmem` / `psave`）的入口条件未知；若能进，可用相机自身 dump ROM。

---

## 10. 复现命令

```bash
# 本轮新增的扫描/分析脚本（工作区，未入库）
python fw-work/find_callers_manual.py      # CALL 编码反查（cd + 低16位位移）
python fw-work/find_art_rom_refs.py        # ROM 描述符引用
python fw-work/art_effect_registry.py      # 滤镜 ID 登记表
python fw-work/verify_patch_patterns.py    # 补丁模式唯一性校验

# 构建
python tools/make_patched_firmware.py --image fw-work/ep5v18/OLY_E_108_1800_0000_0000.BIN \
    --recipe patches/ep5_art_typegate_pattern.json --out out.BIN --report rep.json
```
