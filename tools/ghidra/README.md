# Ghidra + MN10300：让 REA / Ghidra 原生分析奥林巴斯固件

> 2026-10-22 建立
> 目的：Ghidra 官方发行版**不含** Panasonic MN1030/MN103S 处理器模块，
> 而 E-P5 / E-PL3 / E-M1 III 的主控正是 MN1030。
> 本目录提供第三方 SLEIGH 模块 + Olympus 调用约定 + 本项目自写的分析脚本。

---

## 1. 上游来源（已校验 SHA-256）

| 文件 | URL | SHA-256 |
|---|---|---|
| GhidraMn10300 主分支 zip | `https://github.com/txt231/GhidraMn10300/archive/refs/heads/main.zip` | `F52E6BC57AFF8FB12981A1006A79DB8ABE91BA62145504A6E8C4CDCF063BCC4F` |
| `mn103-call.patch` | `https://raw.githubusercontent.com/cmdada/em10-fw/main/tools/ghidra/mn103-call.patch` | `F814841510FA48D9E4958C023DDB946E3173FF56CE33101E67474AA43E9BCF42` |
| `mn103-olympus.cspec` | `https://raw.githubusercontent.com/cmdada/em10-fw/main/tools/ghidra/mn103-olympus.cspec` | `FF5698A8F0F2CE9398113A78962BF28E89641ADCFA1E62E30CA3C6BA8B490A7E` |

> `mn103-call.patch` 修复 `call f,[regs],imm` 的保存寄存器恢复（调用点不再恢复，
> 由被调方的 `RET PopRegsBrace,IMM8` 恢复）。已用 p-code 验证生效。
> `mn103-olympus.cspec` 定义奥林巴斯调用约定：A0/A1 = 指针，D0/D1 = 整数，
> D2/D3/A2/A3 不被调用破坏，栈参数在 `(12+imm, sp)`，返回指针在 A0。

---

## 2. 安装布局

```
C:\Users\21745\tools\ghidra_12.1.4_PUBLIC\Ghidra\Processors\MN103\
  Module.manifest
  data\buildLanguage.xml
  data\sleighArgs.txt
  data\languages\
    am33.sinc  mn103.sinc(已打补丁)  mn103.slaspec  mn103.sla(已编译)
    mn103.pspec  mn103.cspec  mn103-olympus.cspec  mn103.ldefs  mn103.opinion
```

`mn103.ldefs` 注册两个语言 ID（**第一个 compiler spec 即默认**）：

```xml
<language id="MN103:LE:16:default" processor="MN1030" endian="little" size="16" ...>
  <compiler name="default" spec="mn103-olympus.cspec" id="default"/>  <!-- Olympus，默认 -->
  <compiler name="mn103"    spec="mn103.cspec"         id="mn103"/>
</language>
<language id="MN103:LE:32:default" ... size="32" .../>   <!-- 与地址空间等价的别名 -->
```

**两个必须注意的偏差（相对上游）：**

1. **Ghidra 12 已无 `<proc>/<Module>.ldefs`**：12.x 的处理器注册完全靠
   `data/languages/*.ldefs` 里的 `processor=` 属性，没有 `processor_definitions` 根了。
   按上游原样安装会导致 Processor Extension Point 里看不到语言。
2. **地址空间必须 32 位**：镜像装载在 `0x402C0000`，代码里有 32 位绝对地址
   （如 `mov 0x605339a0,d0`），16 位地址空间表达不了。
   `mn103.sinc` 保留 `define space ram ... size=4`；
   ID 仍按 CPU 位宽登记为 `MN103:LE:16:default`（另附 `MN103:LE:32:default` 别名）。

---

## 3. 验证结果（已核对）

与仓库内 GNU objdump 基准**逐指令比对**（窗口 `0x403B7965..0x403B7A30`）：

```
objdump 指令数 (窗口内) : 77
Ghidra  指令数 (窗口内) : 77
地址不匹配 : 0
字节不匹配 : 0
语义不匹配 : 0
结果: AGREE —— 指令边界与语义完全一致
```

**全量能力**（块 0，15,728,576 B）：

| 指标 | 值 |
|---|---|
| 解码指令数 | **6,488,149**（58.8 s） |
| 块内不同引用目标 | 330,783 |
| 块内 CALL 目标 | 58,227 |
| 识别函数数 | **56,984** |
| `0x403B0000..0x40400000`（艺术滤镜区）内函数 | **1,423** |

---

## 4. 命令行

```cmd
set JAVA_HOME=C:\Users\21745\tools\jdk-21.0.12.1+1
set PATH=%JAVA_HOME%\bin;%PATH%
set W=D:\0_Project\01Test\fw-work\ghidra-mn103

REM (A) 导入 + 反汇编抽查
C:\Users\21745\tools\ghidra_12.1.4_PUBLIC\support\analyzeHeadless.bat ^
  %W%\proj mn103_ep5 -import ^
  D:\0_Project\01Test\ep5-fw-reverse\decoded\00_0100_402c0020.decoded.bin ^
  -loader BinaryLoader -loader-baseAddr 0x402c0000 ^
  -processor MN103:LE:16:default -cspec default ^
  -scriptPath %W%\scripts -postScript Mn103Dump.java %W%\out -noanalysis

REM (B) 全量批量反汇编 + 建函数（工程 mn103_full）
C:\Users\21745\tools\ghidra_12.1.4_PUBLIC\support\analyzeHeadless.bat ^
  %W%\proj mn103_full -import ^
  D:\0_Project\01Test\ep5-fw-reverse\decoded\00_0100_402c0020.decoded.bin ^
  -loader BinaryLoader -loader-baseAddr 0x402c0000 ^
  -processor MN103:LE:16:default -cspec default ^
  -scriptPath %W%\scripts -postScript Mn103BulkAnalyze.java %W%\out
```

> `JAVA_HOME` 必须设置，否则 `analyzeHeadless.bat` 找不到 JVM。
> `-loader-baseAddr` 是 BinaryLoader 的 base address 选项，**不需要** `setImageBase` 脚本。
> 已分析工程内的程序名即导入文件名：`00_0100_402c0020.decoded.bin`。

---

## 5. 本项目脚本

| 脚本 | 用途 |
|---|---|
| `Mn103BulkAnalyze.java` | 全镜像线性反汇编 + 在所有 CALL 目标处建函数（产生 56,984 函数） |
| `Mn103Dump.java` | 输出指定地址区间的反汇编 |
| `Mn103FindArtRefs.java` | **扫描全部指令**，找操作数标量落在指定地址区间的引用（用于判定"某字符串是否被引用"） |
| `Mn103FindEffectSwitch.java` | 找出同时比较多个效果 ID（10/20/30/40/50）的函数 |
| `Mn103DumpFuncs.java` | dump 指定函数的完整反汇编 + 调用关系 + 数据引用 |
| `Mn103ArtStringRefs.java` | 对指定地址查询 Ghidra 已知引用（代码 + 数据） |

### 已得到的关键结论

- `Mn103FindArtRefs`（区间 `0x40714000..0x40718000`，art 字符串区）：
  **6,488,149 条指令中 0 条命中**。
- `Mn103ArtStringRefs`（`0x407155B0` = `art_effect_20_pinhole` 等）：
  **引用数 0**，且目标处未定义为字符串对象。
  ⇒ `art_*` 是**残留符号名表**，不能用于定位实现代码（详见 `evidence/art_filter/art_filter_analysis.md` §2）。
- `Mn103FindEffectSwitch`：命中 18 个函数，其中含 4 个不同效果 ID 的 3 个候选：
  `FUN_4047975c` [20,30,40,50]、`FUN_4048b6d2` [10,20,30,40]、`FUN_4049893c` [10,20,30,40]。

---

## 6. 与 REA 的关系 / 已知限制

REA 的 `open_binary` 用 Ghidra provider 时：
- 语言通过 `REA_GHIDRA_LANGUAGE_ID` / `REA_GHIDRA_COMPILER_SPEC_ID` 指定
  （本机设 `MN103:LE:16:default` 与 `default`）。
- ⚠️ **REA 对非 DOS 格式导入不传 base address**（其 `GhidraLauncher.js` 只在
  `dosMz`/`dosCom` 分支里给 `-loader` / `-loader-baseAddr`），
  裸 `.bin` 会被装载在 **base 0**。这不是 Ghidra 模块的问题，是 REA 侧的空缺。
  规避办法二选一：
  1. 本目录的 headless 命令（自带 `-loader-baseAddr`）；
  2. 让 REA 导入 base 0 的镜像，再自行把地址加回 `0x402C0000`
     （文件偏移 = 地址，便于换算）。

---

## 7. 已知风险

- 上游 SLEIGH 自述为 WIP（"unfinished processor module… unsure about accuracy"，
  FPU 指令是 stub）。**已核对的 MN103 核心指令精确**，但 `am33.sinc` 继承来的
  AM33/FPU 指令可信度较低。
- `mn103.pspec` 仍声明 MN10300 评估板 MMIO 窗口（`0xC0000000`，长 `0x20000000`），
  与本镜像不重叠、无报错，但真实 E-P5 的 MMIO 基址是 `0x605339a0`，该块应重新基址化。
- 函数边界由 CALL 目标推导，58,227 个 CALL 目标中有 1,253 个在线性扫描下不是指令起点，
  被跳过 ⇒ **数据区的函数体边界是近似的**。艺术滤镜区不受影响；
  需要精确边界时应以已知入口点播种。
