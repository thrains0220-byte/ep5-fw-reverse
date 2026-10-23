# 社区补丁「模式 A」完整语义解码

> 第 21 轮（2026-10-24）。本文是继第十六轮「首次解出常量 `0x70000010`」之后，
> 把社区改机补丁的**两处改动全部逐指令解码**，并给出 E-P5 v1.8 的对应位置。
>
> 证据等级约定：**【观察】** = 可复现的字节/反汇编事实；**【推断】** = 由观察推导；
> **【未知】** = 当前无法判定。

---

## 0. 结论摘要

| 项 | 内容 |
|---|---|
| 补丁规模 | 社区改机归档的块 0 与原版**只差 2 处**（12 B + 2 B），已在 3 个机型上逐字节核验 |
| 改动 1 | 把「按 AF 步进编号分派、返回步数上限」的查表，换成**写死一个大常量** ⇒ **解除 AF 驱动步数上限** |
| 改动 2 | 把「镜头 ID 未命中白名单 ⇒ 判定未识别」的分支**换成 2 条 NOP** ⇒ **解除镜头 ID 白名单校验** |
| E-P5 v1.8 对应 | 改动 1 在 E-P5 是**内联版**（`FUN_4058a207`），位置已精确定位；改动 2 在 E-P5 **尚未定位** |

---

## 1. 坐标约定（**本轮更正**，务必先读）

历史材料里混用了两套坐标，本轮用 Ghidra 工程 + 原始字节**双重锚定**后统一：

| 坐标系 | 定义 | 用途 |
|---|---|---|
| **Ghidra / 运行地址** | `运行地址 = 块内文件偏移 + 块基址` | 本轮全部反汇编坐标 |
| 容器规范地址 | `运行地址 + 0x20` | `decoded/manifest.json` 的 `container_payload_address` |

各机型块 0 的块基址：

| 机型 | 块基址 | 文件名里的 `…0020` |
|---|---|---|
| E-P5 v1.8 | `0x402C0000` | `00_0100_402c0020` |
| E-M1 II v3.4 / v3.6 | `0x40560000` | `00_0100_40560020` |
| E-M1 v4.6 | `0x40300000` | `00_0100_40300020` |
| E-M1 III v1.2 | `0x40800000` | `00_0100_40800020` |
| E-M5 III v1.4 | `0x40780000` | `00_0100_40780020` |
| E-M10 III v1.2 | `0x406E0000` | `00_0100_406e0020` |
| E-PL9 v1.1 | `0x406E0000` | `00_0100_406e0020` |
| E-M10 II v1.4 | `0x40300000` | `00_0100_40300020` |

> 校验方法：E-P5 块 0 里 9 个 `MOV #imm32, A0` 锚点（`fc dc 78 3c 50 7e` 等）
> 全部满足 `文件偏移 = 运行地址 − 0x402C0000`。
> 工具：`tools/opcode_map.py`、`tools/find_movl_imm.py`

---

## 2. MN10300 指令编码速查（本轮逆向产出，可复用）

由 E-P5 工程 97 132 条指令 + 原始字节对齐统计得出（`tools/opcode_map.py`）：

| 编码 | 助记符 | 说明 |
|---|---|---|
| `a0 XX` | `CMP #XX, D0` | 2 B |
| `c8 XX` | `BEQ +XX` | 2 B，**位移相对本指令地址**，有符号 8 位 |
| `c9 XX` | `BNE +XX` | 2 B |
| `ca XX` | `BRA +XX` | 2 B |
| `c4 XX` | `BCS +XX` | 2 B（无符号 <） |
| `c5 XX` | `BHI +XX` | 2 B（无符号 >） |
| `cb` | **`NOP`** | 1 B |
| `2c XX XX` | `MOV #imm16, D0` | 3 B，imm 小端 |
| `27 XX XX` | `MOV #imm16, A3` | 3 B，imm 小端 |
| `fc cc XX XX XX XX` | `MOV #imm32, D0` | 6 B |
| `fc ce …` / `fc dc …` | `MOV #imm32, D2` / `MOV #imm32, A0` | 6 B |
| `80 01` | `MOV 0x1, D0` | 2 B |
| `f8 92 04` | `MOVBU D0,(0x4,SP)` | 3 B |
| `71` | `MOV (A1), D0` | 1 B |
| `a1` | `CMP D0, D1` | 1 B |

> **`cb` = NOP 是本轮最关键的一条**：社区补丁第 2 处写的 `cb cb` 就是「删掉这条分支」。

---

## 3. 补丁改动 1 —— AF 步数上限查表 → 常量

### 3.1 原函数（E-M1 III v1.2，块 0）

【观察】`FUN_40b232ec` @ 运行地址 `0x40B232EC`，函数体 `0x40B232EC–0x40B23340`（0x54 B），
块内文件偏移 `0x3232EC`。Ghidra 工程 `em1iii12s`（原版 E-M1 III v1.2）。

反汇编（逐条来自 `Mn103DisasmRange`，`fw-work/ghidra-mn103/out/dis_pat_site.txt`）：

```
0x40b232ec  CLR D2
0x40b232ed  EXTHU D0            ; D0 = step
0x40b232ee  CMP 0x6,D0
0x40b232f0  BEQ 0x40b23304
0x40b232f2  CMP 0x3,D0
0x40b232f4  BEQ 0x40b23304
0x40b232f6  CMP 0x8,D0
0x40b232f8  BEQ 0x40b23304
0x40b232fa  CMP 0x9,D0
0x40b232fc  BEQ 0x40b23304
0x40b232fe  CMP 0x4,D0
0x40b23300  BEQ 0x40b23309
0x40b23302  BRA 0x40b2330f
0x40b23304  MOV 0x6cc,D0
0x40b23307  BRA 0x40b2330c
0x40b23309  MOV 0x1c20,D0
0x40b2330c  MOV D0,(A0)          ; *out = 上限
0x40b2330d  BRA 0x40b2333c
0x40b2330f  MOV 0x9d06,D2        ; 错误分支
...
0x40b2332d  MOV 0x39040009,D0
0x40b23333  MOV 0x2,D1
0x40b23335  CALL 0x40843a9f
0x40b2333c  MOV D2,D0
0x40b2333d  EXTHU D0
0x40b2333e  RET [D2],0x1c
```

等价 C：

```c
uint FUN_40b232ec(uint *out, short step) {
    if (step == 6 || step == 3 || step == 8 || step == 9) *out = 0x6CC;   // 1740
    else if (step == 4)                      *out = 0x1C20;                 // 7200
    else { FUN_40843a9f(0x39040009, 2); return 0x9D06; }
    return 0;
}
```

【观察】调用者只有 2 个：`FUN_40b22373`（CALL @ `0x40B2267D`）、`FUN_40b23da4`（CALL @ `0x40B23DC3`）。

### 3.2 这个「上限」是什么

【观察】`FUN_40b23da4` 反编译（`out/decomp_em1iii_callers.txt`）：

```c
ushort FUN_40b23da4(uint *out, ushort step) {
    int c = FUN_40b13f2d(0);
    if (*(char *)(c + 0x2a9) == '\x01') *out = (uint)*(byte *)(c + 0x2a8);
    else                                 uVar2 = FUN_40b232ec(out, step);
    return uVar2;
}
```

【观察】`FUN_40b22373` 的调用点前后（`out/dis_callsite_em1.txt`）：

```
0x40b2266a  MOV (0x14,SP),A0
0x40b2266c  MOV (0x10,SP),D1
0x40b2266e  MOVHU (A0),D0        ; D0 = step
0x40b22670  MOV SP,A0
0x40b22671  ADD 0x3c,A0          ; A0 = 出参槽 SP+0x3c
0x40b22673  CLR D2
0x40b22674  MOV D2,MDR
0x40b22676  MOV 0x258,D2
0x40b22679  DIVU D2,D1
0x40b2267b  MOV D1,A2
0x40b2267d  CALL 0x40b232ec      ; *（SP+0x3c）= 上限
0x40b22682  EXTHU D0
0x40b22683  CMP 0x0,D0
0x40b22685  BNE 0x40b226b3       ; 返回非 0 → 出错
0x40b22687  MOV (0x3c,SP),D2     ; D2 = 刚写入的上限
0x40b22689  MOV A2,D3            ; D3 = 计数
0x40b2268b  CMP D2,D3
0x40b2268c  BCS 0x40b2268f
0x40b2268e  MOV D2,D3            ; D3 = min(上限, 计数)
```

【推断】`0x6CC`(1740) / `0x1C20`(7200) 是 **AF 镜头驱动步数上限**；
`FUN_40b22373` 里 `uVar5 = 0x6cc; if (*puVar8 < 0x6cc) uVar5 = *puVar8;`
是同一套钳位的内联副本（`out/decomp_em1iii_callers.txt`）。
⇒ **改动 1 的作用 = 解除 AF 驱动步数上限**。

### 3.3 补丁后的行为

【观察】打补丁版（工程 `em1iii12p`）同一函数反编译为：

```c
undefined4 FUN_40b232ec(undefined4 *param_1) {
    *param_1 = 0x70000010;
    return 0;
}
```

字节级（块 0 文件偏移 `0x3232ED`，运行地址 `0x40B232ED`）：

```
stock  : 1c a0 06 c8 14 a0 03 c8 10 a0 08 c8
patched: fc cc 10 00 00 70 60 88 1c df 80 1c
```

即 `fc cc 10 00 00 70` = `MOV 0x70000010, D0`，`60` = `MOV D0,(A0)`（**32 位存储**，出参是 `uint *`）。

【推断】`0x70000010` ≈ 1.88×10⁹，作为「上限」等效于**无上限**（钳位 `min(cap, 计数)` 恒取计数）。
错误分支也被一并删掉（原版对 step ∉ {3,4,6,8,9} 报 `0x39040009`）。

### 3.4 各机型的字节与地址

| 机型 | 块内文件偏移 | 运行地址 | stock 字节 | patched 字节 |
|---|---|---|---|---|
| E-M1 III v1.2 | `0x3232ED` | `0x40B232ED` | `1c a0 06 c8 14 a0 03 c8 10 a0 08 c8` | `fc cc 10 00 00 70 60 88 1c df 80 1c` |
| E-M1 II v3.4 | `0x33399F` | `0x405F399F` | 同上 | 同上 |
| E-M5 III v1.4 | `0x316B1C` | `0x405D6B1C` | 同上 | 同上 |
| E-M10 III v1.2 | `0x3213BC` | `0x405E13BC` | 同上 | 同上 |
| E-PL9 v1.1 | `0x312C09` | `0x405D2C09` | 同上 | 同上 |
| E-M1 v4.6 | `0x378839` | `0x40638839` | `1c a0 06 c8 0c a0 03 c8 08 a0 04 c8`（A2 变体，比较 6/3/4） | `fc cc 10 00 00 70 60 88 1c df 80 08` |
| E-M1 II v3.6 | `0x3339B3` 起 3 段 | `0x405F39B3` 起 | `09`→`04`、`2c`→`fc`、`06 ca 05 2c 20 1c` | `70 70 70 70 cb cb`（写常量 `0x70707070` + 2×NOP，BEQ 位移同步调整） |
| E-M10 II v1.4 | `0x50D52B` | `0x405FD52B` | `1c a0 06 c8 0c a0 03 c8 08 a0 04 c8` | `fc cc 10 00 00 70 60 88 1c df 80 08` |

---

## 4. 补丁改动 2 —— 镜头 ID 白名单校验

### 4.1 原函数（E-M1 III v1.2）

【观察】`FUN_40e773c9` @ 运行地址 `0x40E773C9`，块内文件偏移 `0x6773C9`。
该函数把 `0x6079E3A9` 起的 0x30 字节密钥拷到栈上，然后在**镜头 ID 表**里线性搜索：

```
0x40e773ec  CALL 0x409f7005            ; 取镜头信息数组
0x40e773f3  CMP 0x0,A0
0x40e773f5  BEQ 0x40e77437             ; 无镜头信息 → 未识别
0x40e773f7  ADD 0x444,A0               ; 镜头 ID 字段（3 字节：+0x444/+0x445/+0x446）
0x40e773fb  MOVBU (0x1 ,A0),D1
0x40e773fe  MOVBU (A0),D0
0x40e77400  MOVBU (0x3 ,A0),D2
0x40e77403  MOVBU (0x2 ,A0),D3
0x40e77406  ASL 0x8,D2
0x40e77409  OR D3,D2
0x40e7740b  ASL 0x18,D1
0x40e7740e  OR D1,D2
0x40e77410  ASL 0x10,D0
0x40e77413  OR D0,D2                   ; D2 = 24 bit 镜头 ID
0x40e7741b  MOV (0x8,SP),D0            ; D0 = 待查密钥
0x40e7741d  MOV 0xff,D1                ; D1 = 0xFFFFFFFF 表尾哨兵
0x40e7741f  CMP D0,D1
0x40e77420  BEQ 0x40e7742e
0x40e77422  CMP D0,D2
0x40e77423  BEQ 0x40e7742e             ; 命中 → 退出循环
0x40e77425  SETLB
0x40e77426  INC4 A0
0x40e77427  MOV A0,A1
0x40e77428  MOV (A1),D0               ; 下一个表项
0x40e77429  CMP D0,D1
0x40e7742a  BEQ 0x40e7742e             ; 哨兵 → 退出循环
0x40e7742c  CMP D0,D2
0x40e7742d  LNE                        ; 不等则继续
0x40e7742e  MOV (A1),D0
0x40e7742f  CMP D0,D1                  ; ★ 表尾哨兵？
0x40e77430  BEQ 0x40e77437             ; ★★ 补丁点：命中哨兵 → 判「未识别」
0x40e77432  MOV 0x1,D0
0x40e77434  MOVBU D0,(0x4,SP)          ; 置「已识别」标志 = 1
0x40e77437  ...
```

### 4.2 补丁

【观察】块 0 文件偏移 `0x677430`（运行地址 `0x40E77430`）：

```
stock  : c8 07        ; BEQ +7  → 跳到「未识别」
patched: cb cb        ; NOP NOP
```

Ghidra 对补丁版的解码（工程 `em1iii12p`）确认 `0xcb` = **NOP**：

```
0x40e7742f  CMP D0,D1
0x40e77430  NOP
0x40e77431  NOP
0x40e77432  MOV 0x1,D0
0x40e77434  MOVBU D0,(0x4,SP)
```

【推断】删掉哨兵判断后，**无论镜头 ID 是否在白名单表里，都走到 `MOV 0x1,D0`，
把「已识别」标志置 1** ⇒ **解除镜头 ID 白名单校验**（让表外镜头也被当作已识别/支持）。

### 4.3 各机型坐标

| 机型 | 块内文件偏移 | 运行地址 | stock | patched |
|---|---|---|---|---|
| E-M1 III v1.2 | `0x677430` | `0x40E77430` | `c8 07` | `cb cb` |
| E-M1 II v3.4 | `0x635A7B` | `0x40B95A7B` | `c8 07` | `cb cb` |
| E-M1 II v3.6 | `0x635A2A` | `0x40B95A2A` | `c9 04` | `cb cb` |
| E-M1 v4.6 | `0x1D215D` | `0x404D215D` | `c8 07` | `cb cb` |
| E-M5 III v1.4 | `0x63D61D` | `0x40DBD61D` | `c8 07` | `cb cb` |
| E-M10 III v1.2 | `0x6055D7` | `0x40CE55D7` | `c8 07` | `cb cb` |
| E-PL9 v1.1 | `0x5F79AB` | `0x40CD79AB` | `c8 07` | `cb cb` |

> 【观察】`c8 07` 前 16 字节上下文 `c8 0e a2 c8 0b db 50 91 71 a1 c8 04 a2 d9 71 a1`
> 在**每个机型里唯一命中**（E-PL9 另有 1 处上下文相同但分支是 `c9 07`）。
> 【观察】**E-P5 v1.8 中该上下文 0 命中** ⇒ E-P5 的白名单校验函数结构不同，见 §6。

---

## 5. 改动 1 的「跨机型指纹」为什么在 E-P5 落空

【观察】24 字节指纹 `1c a0 06 c8 14 a0 03 c8 10 a0 08 c8 0c a0 09 c8 08 a0 04 c8`
在 E-M1 II v3.0/v3.4、E-M1 III v1.2、E-M5 III v1.4、E-M10 III v1.2、E-PL9 v1.1 里
**各唯一命中且偏移完全吻合**；在 E-M1 v4.6（A2 变体）0 命中；在 **E-P5 v1.8 0 命中**。

【推断】E-P5 把这段逻辑**内联进了更大的函数**，所以字节级指纹不匹配 —— 这也说明
**不能靠字节比对跨机型定位，必须靠「标量常量 + 调用图」**（见 §6 的做法）。

---

## 6. E-P5 v1.8 的对应实现

### 6.1 定位方法

【观察】用新写的 Ghidra 脚本 `tools/ghidra/Mn103FindScalarConst.java`
（在已分析的 program 里按**标量立即数**和**比较链**两类特征定位函数）：

* 在 E-M1 III 工程上，唯一同时引用 `0x6CC` 与 `0x1C20` 的函数正是 `FUN_40b232ec`（方法学自检通过）。
* 在 E-P5 工程（`mn103_full`）上，**唯一**同时引用 `0x6CC` 与 `0x1C20` 的函数是
  **`FUN_4058A207`**（`0x4058A207`，函数体 `0x4058A207–0x4058A39B`，块内文件偏移 `0x2CA207`）。

### 6.2 E-P5 的函数本体（反编译要点）

```c
int FUN_4058a207(ushort step, uint param_2) {
    int ctx = FUN_40589935();
    uint cap = 0;                       // 上限
    int  cnt = 0;                       // 每步分母
    uint thr;                           // 阈值
    uint mode = FUN_40300647(0, 0x6671, 0) & 0xff;
    char flag = FUN_40300647(0, 0x8151, 7);
    FUN_4056cead(0x7e503c78, 0x10, param_2);      // ← mask ROM 参数表

    if (mode == 3) {
        base = 0x177;
        if      (step == 6 || step == 3) thr = 0x340;
        else if (step == 4)              thr = 0xa40;
        else error(0x7e503c87);
    } else { base = 0x2f; thr = 400; }

    if (param_2 <= thr) { steps = 0; steps2 = 0; goto store; }

    if (mode == 3) {
        if (step == 6)      { cnt = 0x1313; if (flag != 1) cnt = 0x1037; }
        else if (step == 3) { cnt = 0xc66;  if (flag != 1) cnt = 0x98a;  }
        else if (step == 4) { cnt = 0x3d1;  cap = 0x1c20; }
        else error(0x7e503c87);
        cap = 0x6cc;
    } else if (mode == 2) {
        if (step == 5)      { cnt = 0x16e4; if (flag != 1) cnt = 0x1267; }
        else if (step == 3) { cnt = 0x1267; if (flag != 1) cnt = 0xfcd;  }
        else error(0x7e503ca5);
        cap = 0x6cc;
    } else error(0x7e503cc6);

    steps  = (param_2 - thr) / (cnt + base);
    steps2 = (0x800000 - thr) / (cnt + base);
    if (steps2 <= cap) cap = steps2;
    if (cap <= steps)  steps2 = cap;

  store:
    *(uint *)(ctx + 0x20) = steps  * 0x1e;
    *(uint *)(ctx + 0x24) = steps  * 0x1e;
    *(uint *)(ctx + 0x28) = steps2 * 0x1e;
    FUN_4056cead(0x7e503ce3, 0x10, steps);
    FUN_4056cead(0x7e503cf2, 0x10, steps2);
    return steps * 600;
}
```

【观察】**step 编号集合 {6,3,4} 与上限常量 {0x6CC, 0x1C20} 与社区改机机型完全一致**
⇒ 同一功能的**内联版**（社区改机机型上被拆成 helper `FUN_40b232ec`）。

【观察】E-P5 版还引用 **mask ROM** 地址：
`0x7E503C78`（参数表）、`0x7E503C87` / `0x7E503CA5` / `0x7E503CC6`（错误串）、
`0x7E503CE3` / `0x7E503CF2`（输出表）。

【观察】E-P5 里该函数只有 **1 个调用者**：`FUN_40589970`（CALL @ `0x4058998B`），
调用点上下文里同样有 `CMP 0x3,D0`。

### 6.3 E-P5 上「上限常量」的确切字节

| 常量 | 运行地址 | 块内文件偏移 | 原字节 | 指令 |
|---|---|---|---|---|
| `0x6CC` | `0x4058A31F` | `0x2CA31F` | `27 cc 06` | `MOV 0x6cc,A3` |
| `0x1C20` | `0x4058A2DF` | `0x2CA2DF` | `27 20 1c` | `MOV 0x1c20,A3` |

（坐标校验：E-P5 块 0 里 9 个 `MOV #imm32,A0` 锚点全部满足 `off = addr − 0x402C0000`。）

### 6.4 效果估算（**推断，非实测**）

【推断】E-P5 的钳位不是唯一约束：真正的上限还来自
`steps2 = (0x800000 − thr) / (cnt + base)` 这条 24 位量程公式。按各分支代入：

| mode | step | cnt | base | thr | 量程上限 | 钳位 cap | 谁在起作用 | 抬高 cap 后 |
|---|---|---|---|---|---|---|---|---|
| 3 | 6 | 0x1313 | 0x177 | 0x340 | 1595 | 1740 | 量程 | **不变** |
| 3 | 3 | 0xC66 | 0x177 | 0x340 | 2363 | 1740 | **cap** | 1740 → 2363（+36%） |
| 3 | 3 | 0x98A | 0x177 | 0x340 | 2977 | 1740 | **cap** | 1740 → 2977（+71%） |
| 3 | 4 | 0x3D1 | 0x177 | 0xA40 | 6202 | 7200 | 量程 | **不变** |
| 2 | 5 | 0x16E4 | 0x2F | 0x190 | 1419 | 1740 | 量程 | **不变** |
| 2 | 3 | 0x1267 | 0x2F | 0x190 | 1763 | 1740 | **cap** | 1740 → 1763（+1%） |

⇒ **重要结论**：在 E-P5 v1.8 上，社区补丁那种「上限写成 0x70000010 ≈ 无上限」的效果，
**不能只靠改这两个常量拿到**。E-P5 的 `0x800000` 量程公式才是多数分支的真正瓶颈。
要把上限彻底放开，还需一并抬高 `0x800000`（`0x4058A256` 与 `0x4058A28C`，
文件偏移 `0x2CA256` / `0x2CA28C`，字节 `fc cc 00 00 08 00`），
但输出按 `steps × 0x1e` 存进 u32，抬高量程会引入**溢出风险**，必须实机验证。

---

## 7. 未完成项

| 项 | 状态 | 下一步 |
|---|---|---|
| E-P5 v1.8 中「镜头 ID 白名单校验」的对应函数 | **未定位** | E-P5 的白名单表/镜头 ID 结构偏移与社区机型不同，字节指纹 0 命中。需先在 E-P5 里定位「镜头信息数组取用器」（E-M1 III 的 `FUN_409f7005`）与「镜头 ID 24 位拼装」模式（`ASL 0x8 / OR / ASL 0x18 / OR / ASL 0x10 / OR`） |
| E-P5 上限抬高后的实机效果 | **未验证** | 需实机刷写 + 抓 AF 行程日志 |
| 社区补丁在 E-M10 II v1.4 / E-M5 III 等其它归档是否还有第 3 处改动 | **未全查** | 已查 8 个归档、6 个确认恰好 2 处；`em5ii41b/c`、`pen_f_v31` 等尚未逐字节核验 |

### 7.1 第二十一轮已排除的 E-P5 定位路径（避免重复劳动）

针对「白名单校验函数在 E-P5 的对应位置」，本轮已试过并**排除**下列路径
（工具：`tools/find_whitelist_pattern.py`）：

| # | 搜索模式 | E-P5 v1.8 结果 |
|---|---|---|
| 1 | 16 字节上下文 `c8 0e a2 c8 0b db 50 91 71 a1 c8 04 a2 d9 71 a1` | **0 命中** |
| 2 | 紧邻模式 `71 a1 c8/c9 XX 80 01 f8 92 04`（完整指令序列） | **0 命中** |
| 3 | 松模式 `c8/c9 XX 80 01 f8 92 04` | 42 命中（全是「置标志位=1」的通用惯用法，非白名单） |
| 4 | `71 a1 c8/c9 XX 80 01`（放宽到 4 字节内） | **0 命中** |
| 5 | `71 a1 c8/c9 XX`（再放宽） | 33 命中（其中 0x404CDA99 已反汇编核对 = 事件链表函数；0x40D54D6F = `a<=b` 比较助手） |
| 6 | `MOV 0xff,D1` + `CMP D0,D1` + 紧邻分支 | **0 命中** |
| 7 | 0x30 字节拷贝循环 `MOVBU (A1),D0 / INC A1 / MOVBU D0,(A0)`（E-M1 III 白名单表的载入方式） | 7 命中，**全部是从 mask ROM 拷字符串/表**（长度 0x80/0xF8/0xFB/0xFF54，源地址全在 `0x7Exxxxxx`），无一是 RAM 白名单表 |

⇒ **推断**：E-P5 的白名单校验**没有采用 E-M1 III 的「拷表 + 线性搜索」结构**，
或它的表长度 / 寄存器用法 / 标志位存储位置都变了。
⇒ 下一步应改用**语义锚点**而非字节锚点：
`FUN_409f7005`（镜头信息数组取用器）与 `FUN_40e76c68`（镜头信息有效性判定）
在 E-P5 的对应函数，再从其调用者里找「按 4 字节 ID 比对 + 0xFFFFFFFF 哨兵」的那一处。

---

## 8. 本轮新增工具

| 工具 | 作用 |
|---|---|
| `tools/patch_diff.py` | 任意两个块 0 的逐字节差异，连续段分组 |
| `tools/opcode_map.py` | Ghidra 反汇编 + 原始字节对齐，反推 opcode↔助记符表 |
| `tools/find_movl_imm.py` | 块 0 内精确扫描 `MOV #imm` 立即数 |
| `tools/find_whitelist_pattern.py` | 跨机型找白名单校验函数的字节模式 |
| `tools/find_dispatch_by_fingerprint.py` | 按比较链指纹跨机型定位分派函数 |
| `tools/ghidra/Mn103FindScalarConst.java` | 在 Ghidra program 里按标量常量 / 比较链定位函数 |

## 9. 复现命令

```powershell
# 补丁差异
python tools/patch_diff.py --pairs "fw-work\patched\e-m1-iii-v12_sdec=fw-work\patched\e-m1-iii-v12_pdec"

# opcode 表（需先有 Ghidra 反汇编输出）
python tools/opcode_map.py --blk0 decoded\00_0100_402c0020.decoded.bin --base 0x402C0000 --disasm <disasm.txt>

# Ghidra 侧：标量常量搜索
fw-work\ghidra-mn103\scalar.bat mn103_full 00_0100_402c0020.decoded.bin scalar_ep5.txt imms.txt
fw-work\ghidra-mn103\decomp_file.bat mn103_full 00_0100_402c0020.decoded.bin decomp_ep5_dispatch.txt addr_ep5_dispatch.txt
fw-work\ghidra-mn103\disasm_range.bat em1iii12p 00_0100_40800020.decoded.bin dis_site2p2.txt 0x40e77420 0x40e77450
```
