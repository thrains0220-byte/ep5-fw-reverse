# 社区"解锁"补丁的语义：把「按模式取值」的分派器换成常量

> 日期：2026-10-22（第十四轮续）
> 配套：`evidence/patched_community/community_patch_table.md`（字节表）
> 方法：把**已打补丁的**固件块 0 单独导入 Ghidra，直接反编译补丁点所在函数。
> 性质：**观察（静态）**。这是本项目第一次读出社区改机补丁的**语义**而不只是字节。

---

## 0. 一句话结论

> **社区改机的"解锁"= 把一个「读入模式 ID → 按 ID 分派/取值 → 写回」的函数，
> 整体替换成「无条件写一个固定常量」。**
>
> 补丁后的代码只有 7 条指令、12 字节，与被替换的 12 字节**等长**，
> 所以不用移动任何代码 —— 这是社区能做到"最小手术"的原因。

---

## 1. 方法

`tools/patched_batch.py` 已经把 12 个社区归档解混淆成块 0。
取其中 **E-M1 III v1.2** 的打补丁块 0：

```
fw-work/patched/e-m1-iii-v12_pdec/00_0100_40800020.decoded.bin   (27,262,912 B, 块 0 基址 0x40800000)
```

用 `import_only.bat` 导入独立 Ghidra 工程 `em1iii12p`
（`-loader-baseAddr 0x40800000 -processor MN103:LE:16:default`），
再用 `seed.bat` 在补丁点附近播种函数（`0x40AF0000`–`0x40B40000`，
seeds=2278, created=901），最后 `Mn103DecompileFile.java` 反编译。

> **可复现的关键点**：本项目所有结论都来自**原版**固件；
> 这一轮是**第一次**把**打补丁的版本**作为分析对象，
> 于是可以直接「读出社区改机到底改了什么」。

---

## 2. 补丁点的指令与伪代码

**模式 A 的补丁点**（E-M1 III v1.2，decoded `0x3232ED`，flash `0x40B232ED`）：

```
stock  : 1c a0 06 c8  14 a0 03 c8  10 a0 08 c8
patched: fc cc 10 00  00 70 60 88  1c df 80 1c
```

**补丁后**的完整函数（body = `0x40B232EC..0x40B232F8`，共 12 字节）：

```
0x40b232ec  CLR D2
0x40b232ed  MOV 0x70000010,D0      ← 补丁写入的常量
0x40b232f3  MOV D0,(A0)
0x40b232f4  MOV D2,D0
0x40b232f5  EXTHU D0
0x40b232f6  RET [D2],0x1c
```

伪代码：

```c
undefined4 FUN_40b232ec(undefined4 *param_1)
{
  *param_1 = 0x70000010;
  return 0;
}
```

### 2.1 被替换掉的是什么

**紧邻的下一个函数**（`0x40B232F9`）是**完全同型**的 switch，
可以作为"原版该长什么样"的直接参照：

```
0x40b232f9  CLR D3
0x40b232fa  CMP 0x9,D0
0x40b232fc  BEQ 0x40b23304
0x40b232fe  CMP 0x4,D0
0x40b23300  BEQ 0x40b23309
0x40b23302  BRA 0x40b2330f
0x40b23304  MOV 0x6cc,D0      ← case 9 的取值
0x40b23307  BRA 0x40b2330c
0x40b23309  MOV 0x1c20,D0     ← case 4 的取值
0x40b2330c  MOV D0,(A0)
```

⇒ **这两个函数是同一类东西**：「给定一个模式 ID，返回/写入一个对应的值」。
社区把其中一个换成了常量版本。

### 2.2 模式 B 的补丁点（`c8 07` → `cb cb`）

E-M1 III v1.2 的 flash `0x40E77430`（decoded `0x677430`）落在
`FUN_40e773c9` 内：

```c
undefined1 FUN_40e773c9(void)
{
  ...
  uVar7 = 0;
  ... 从 0x6079e3a9 拷 0x30 字节到栈 ...
  cVar5 = FUN_40e76c68();
  if ((cVar5 == '\x01') && (iVar6 = FUN_409f7005(0), iVar6 != 0)) {
    puVar3 = (uint *)&stack0x00000008;
    while ((in_stack_00000008 != 0xffffffff &&
           (((uint)*(byte *)(iVar6 + 0x444) << 0x10 |
             (uint)*(byte *)(iVar6 + 0x445) << 0x18 |
             (uint)*(ushort *)(iVar6 + 0x446)) != in_stack_00000008))) {
      puVar3 = puVar3 + 1;
      in_stack_00000008 = *puVar3;
    }
    uVar7 = 1;
  }
  if ((uRam621c1ee8 & 0x200) != 0) {
    FUN_40f22b04(0x6079e3d9, uVar7);
  }
  return uVar7;
}
```

⇒ 模式 B 把一处 `beq +7` 改成 `beq -37`（`c8 07` → `cb cb`），
**跳过了一个"命中即置位 `uVar7 = 1`"的分支** ——
即**取消某个条件的命中处理**，让函数永远走"未命中"路径。

---

## 3. 抽象出来的「解锁模板」

| 步骤 | 做法 |
|---|---|
| 1 | 找到「按模式/能力 ID 分派」的函数（特征：`cmp imm8,d0` + `beq` 链） |
| 2 | 把整条链换成一条**常量赋值**（`MOV imm32,D0 ; MOV D0,(A0)`），**等长**覆盖 |
| 3 | 或把某条 `beq` 改成分支到别处（2 字节），跳过该 case |
| 4 | 重算容器尾校验和（sum32），重新打包 |
| 5 | 刷机 |

⇒ **对 E-P5 的直接含义**：解锁不需要新代码，
只需要在 E-P5 里找到**同一类"按能力 ID 分派"**的函数，改 2~12 字节。
社区在 9 个机型上打的是**同一处**判定 ⇒ 这类判定是**产品线通用**的，
E-P5（E-M5 同代）大概率也有对应处。

---

## 4. E-P5 v1.8 侧的同型分派器清单（本轮新定位）

用 `tools/find_opcode_pattern.py` 在 E-P5 块 0 里搜 `1c a0 06 c8`（`cmp 6,d0`+`beq`）
共 **7 处**，逐个反编译后语义各不相同：

| 函数 | runtime | 语义 | 社区模式对应？ |
|---|---|---|---|
| `FUN_4038df34` | `0x4038DF34` | 位域打包器（case 6/7/8） | 形态相近，语义不同 |
| `FUN_403e7e94` | `0x403E7E94` | **按类型码返回 mask ROM 描述符**（见 §5） | — |
| `FUN_404370ec` | `0x404370EC` | 位域判定（`+0x1c` 的 0x10/0x20/0x80） | — |
| `FUN_4043c40d` | `0x4043C40D` | 空函数（`return 0`） | — |
| `FUN_404b8aaf` | `0x404B8AAF` | 模式 ID `0..6` → 值 `3..10` 的映射 | **最接近社区补丁形态** |
| `FUN_404d5826` | `0x404D5826` | 模式 ID `0..7` 原样返回（其余报错） | — |
| `FUN_4051b16a` | `0x4051B16A` | **按模式 ID `6/10/11/27/28/29/30` 分派到 7 个处理函数** | 形态相近，语义不同 |

### 4.1 `FUN_404b8aaf` —— 与社区补丁点最同型

```c
void FUN_404b8aaf(int *param_1)
{
  int iVar1;  undefined4 uVar2;
  iVar1 = *param_1;
  if      (iVar1 == 0) uVar2 = 3;
  else if (iVar1 == 1) uVar2 = 4;
  else if (iVar1 == 2) uVar2 = 5;
  else if (iVar1 == 3) uVar2 = 6;
  else if (iVar1 == 4) uVar2 = 7;
  else if (iVar1 == 5) uVar2 = 9;
  else { if (iVar1 != 6) return; uVar2 = 10; }
  FUN_404b8b16(uVar2);
}
```

原始字节（`rt 0x404B8AC7` 处）：
`1c a0 03 c8 | 1c a0 04 c8 | 1c a0 05 c8 | **1c a0 06 c8** | 1c a0 07 c8 | 1c ca ...`

⇒ 与社区补丁点同型，但**case 值不同**（E-P5 是 0..6 连续，社区是 3/6/8 离散）
⇒ **这是 E-M5/E-P5 代码库的另一个版本**，社区打的那个判定在 E-P5 里**不是这一处**。

### 4.2 `FUN_4051b16a` —— 7 路处理分派

```c
undefined2 FUN_4051b16a(int param_1, undefined4 param_2, short param_3, undefined4 param_4)
{
  if      (param_3 == 6)   { *(u8*)(param_1+0xe) = 6;   return FUN_4051b1f3(param_4,param_2); }
  else if (param_3 == 10)  { *(u8*)(param_1+0xe) = 10;  return FUN_4051b34c(param_4,param_2); }
  else if (param_3 == 0xb) { *(u8*)(param_1+0xe) = 0xb; return FUN_4051b387(param_4,param_2); }
  else if (param_3 == 0x1b){ *(u8*)(param_1+0xe) = 0x1b;return FUN_4051b443(param_4,param_2); }
  else if (param_3 == 0x1c){ *(u8*)(param_1+0xe) = 0x1c;return FUN_4051b5d1(param_4,param_2); }
  else if (param_3 == 0x1d){ *(u8*)(param_1+0xe) = 0x1d;return FUN_4051b70c(param_4,param_2); }
  else if (param_3 == 0x1e){ *(u8*)(param_1+0xe) = 0x1e;return FUN_4051b780(param_4,param_2,param_2); }
  else return 1;
}
```

**注意 `0x1c` / `0x1d`**：这与 §1 命名空间 B 的 `art_filter_1c_mirror` / `art_filter_1d_composite`
**数值完全一致**（28 / 29）。
⇒ **观察**：E-P5 存在一个以 `6/10/11/27/28/29/30` 为 ID 的 7 路分派器，
其中 28 / 29 与艺术滤镜 ID 空间 B 的 mirror / composite 撞号。
**是否同一套 ID 空间：未定**（需继续追 `FUN_4051b1f3` 等 7 个子函数）。

---

## 5. `FUN_403e7e94` —— 「菜单项清单在 mask ROM」的直接代码证据

```c
undefined4 FUN_403e7e94(void)
{
  int unaff_A2;  char cVar1;
  if (((unaff_A2 != 0) &&
       (cVar1 = FUN_403ed4b4(*(undefined1 *)(unaff_A2 + 0x6b)), cVar1 != '\0')) &&
      (cVar1 != '\x01')) {
    if ((cVar1 == '\x02') || (cVar1 == '\x03')) return 0x7e452be4;
    if (cVar1 == '\x04')                          return 0x7e452bec;
    if (cVar1 == '\x05')                          return 0x7e452bf4;
    if (cVar1 == '\x06')                          return 0x7e452bfc;
  }
  return 0x7e452bdc;
}
```

- **按类型码（`+0x6b` 处的字节）返回 5 个不同的 mask ROM 地址**，
  相邻 8 字节：`0x7E452BDC / BE4 / BEC / BF4 / BFC`。
- 类型码 `0x02` 与 `0x03` **共用**同一个描述符。

⇒ **这直接印证了第十四轮的核心结论**：
「菜单项的组成在机身 mask ROM 里，块 0 只能引用不能新增」。
⇒ 也提供了**判定「录像菜单只有 4 项」的钥匙**：
若录像路径只走到其中 4 个类型码，就只会显示 4 个条目。
**下一步**：追这 5 个描述符在 mask ROM 里的内容（需实机 dump），
并找出谁调用 `FUN_403e7e94`、录像/照片各传什么类型码。

---

## 6. 尚未解决

| # | 问题 |
|---|---|
| 1 | 社区补丁在 E-P5 的**精确对应点**未定（字节特征不匹配，需语义定位） |
| 2 | `FUN_4051b16a` 的 7 个 ID 与 `art_filter_<hex>` 命名空间 B 是否同一套 |
| 3 | `FUN_403e7e94` 的 5 个 mask ROM 描述符内容（需实机） |
| 4 | 模式 B（`c8 07` → `cb cb`）在 E-P5 的对应点（需语义定位） |
| 5 | 补丁写入的常量 `0x70000010` 的语义（E-P5 块 0 内**不存在**该立即数） |

---

## 7. 复现

```sh
# 1) 用完整版 7-Zip 解社区归档（7zr.exe 不含 RAR 解码器）
#    tools/patched_batch.py 已内置

# 2) 把打补丁的块 0 导入独立 Ghidra 工程
fw-work/ghidra-mn103/import_only.bat \
    fw-work/patched/e-m1-iii-v12_pdec/00_0100_40800020.decoded.bin em1iii12p 0x40800000

# 3) 播种函数并反编译补丁点
fw-work/ghidra-mn103/seed.bat em1iii12p 00_0100_40800020.decoded.bin seededp.txt 0x40AF0000 0x40B40000
fw-work/ghidra-mn103/decomp_file.bat em1iii12p 00_0100_40800020.decoded.bin patchsite.txt addr_patchsite.txt

# 4) 在 E-P5 里找同类分派器
python tools/find_opcode_pattern.py --blk decoded/00_0100_402c0020.decoded.bin \
    --pat "1c a0 06 c8" --ctx 12
```
