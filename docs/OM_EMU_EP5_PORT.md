# om-emu → E-P5 (E108) 移植评估记录

目标：用 flatpanda/om-emu 在**不刷机**的前提下运行 E-P5 原厂固件的菜单/GUI，为独立 LUT 菜单提供可复现验证环境。本文记录实际到达的里程碑与阻塞点；所有结论以命令输出为准，不声称未验证的能力。

## 环境

- 上游：`build/research/om-emu-full`，浅克隆，HEAD `4b24000b0a17fde4a810952c3de4fd1ec046a77d`（与父任务克隆的 `build/research/om-emu` 同一提交；后者是 blobless 克隆，checkout 需要联网取 blob，已改用完整浅克隆）。
- Node：本机 v24.14.0。上游 README 要求 node 26（v26.11.1 测试）；v24 目前能解析并运行 `modelcheck`/`fetch-fw`/facts 规则，尚未遇到必须 26 的语法。若后续遇到，再评估下载 node 26。
- E-P5 官方 1.8：`data/ep5-stock/OLY_E_108_1800_0000_0000.BIN`（SHA-256 `cc59a4e1…`，与项目既有校验一致）。

## 里程碑 1：解包与哈希（已通过）

`node build/research/om-emu-full/tools-ep5/unpack-e108.mjs` 用上游 JS 解包器（`emu/src/fw/olyfw.mjs`）解包官方 BIN：

| 块 | 偏移 | flags | 加载地址 | 长度 |
|---|---|---|---|---|
| MAIN | 0x0 | 0x0100 | 0x402c0000 | 15,728,576 |
| 资源 | 0xf00000 | 0x0101 | 0x427c0000 | 22,937,536 |
| 其他 | 0x24e0000 | 0x0106 | 0x43da0000 | 2,490,304 |
| 其他 | 0x2740000 | 0x0104 | 0x44000000 | 3,669,952 |

- MAIN SHA-256 `dfe255e4d5a43329712c1fdfd6861ee1f3ef54a268b6096628bf045d8cc590df`，与本项目 `data/ep5-decoded/00_0100_402c0020.decoded.bin` 完全一致。
- 资源索引 70 项，origin `0x427c0020`，前缀（lab 可读部分）12,936,160 字节，SHA-256 `db8574f82bbaeef07ec01076a2bff630bf053f02ae16f6b012457af3f2cbf2f9`。
- 两块写入 `build/research/om-emu-full/unpacked/E108/`。

## 里程碑 2：上游 facts 规则在 E-P5 上的读数（部分通过）

`node build/research/om-emu-full/tools-ep5/probe-facts.mjs`（完整输出 `tools-ep5/probe-facts.out.txt`）。
注意记法：上游规则输出 `0x50000000+块偏移`（CODE_BASE 记法），换算到 CPU 地址要加 `image_base-0x50000000`；E-P5 的 `image_base=0x7e101020`，即 **CPU = 输出 + 0x2e101020**。

能读出的关键事实（已换算为 CPU 地址）：

| 事实 | 值 | 说明 |
|---|---|---|
| imageBase | `0x7e101020` | reset head 跳转 `0x7e101115`，与本项目 CPU_BASE 一致 |
| resetHead | 6 条拷贝行 | 含 flash→RAM 原位拷贝与 preload；vector page `0x7e110000` |
| guiTask | `0x7eab78e8` | "[GUI App]:Start Gui Task" 字符串引用，唯一 |
| guiTake | `0x7eab7b0a` | GUI 消息接收循环，唯一 |
| kernelCpus | 2 | 双核 |
| displayQueue | word `0x7e11fa30`，id 0x9e | 显示队列 |
| displayTaskInit | `0x7e387f1a` | 创建 DISPLAY 队列的函数 |
| errlogEntry | `0x7e106f3f` | 错误日志入口 |
| brokerInit | `0x7e5860f0` | 事件 broker |
| shotsQuery | `0x7e363c99` | 剩余张数查询 |
| cardDetect | 表 `0x605713b4`，2 驱动器 | |
| mediaStatus / mountState | `0x602b2338` / `0x602b2348` | |
| propStore | init `0x7e355cd2`，objects `0x605dbba8` | 设置存储 |
| ctorTables | `0x7e586184`(7)、`0x7e9afd58`(29)、`0x7ee5cc58`(44) | 组件构造表 |
| cbsIds | 全套拍摄回调 id | 与 E143 同枚举不同值 |
| touchIntWait / touchOpen | 有 | 触屏存在 |
| deferredCalls | init `0x7e14cd57`，triggers `0x9a1000f4` | 注意 MMIO 基址与 E118 族不同（0x9a1… vs 0x9b8…） |

失败/缺口的规则（E-P5 与参考机型结构不同，需要专门适配）：

- `resLoader`：找到索引读取，但后续 0 个 font/string 槽加载（E-P5 资源加载器形式不同）。
- `shootingService`：字符串命中 1 次、加载 2 次，规则要求各 1 次。
- `dcfCounts`：无 DCF 计数 getter（旧文件系统结构）。
- `guiCanvas`：0 个 bank 0xb 设置（E-P5 的 OSD bank 布局不同；E108 本就没有 0x9c100000 独立 OSD 引擎）。
- `listMenu=false`、`menuMemory=undefined`、`dialSelect=undefined`、`fileSystem=undefined`、`sioDriver=undefined`、`bootState` 全 null、`sectionLoader=null`、`mmInit=null`：E-P5 属旧菜单框架（Menu_Viewer/Cursor_2CNL 一类），且启动/文件系统结构与 E143 差异大。

## 里程碑 3：最小 MODELS 条目与 Windows 兼容（进行中）

- 在克隆内 `emu/src/fw/models.mjs` 增加 `E108` 条目：哈希/基址/面板为实测；`board.family: 'E118'` 只是**占位**，E118 族的 INTC/定时器/VSC/OSD 寄存器布局**未在 E-P5 验证**（survey 明确 E108 无 0x9c100000 OSD 引擎，MMIO 细节需另做 census）。
- 上游代码用 `new URL(...).pathname` 推导仓库路径，在 Windows 上产生 `D:\D:\...` 双重盘符。`tools-ep5/win-paths.mjs` 把 51 个文件的这类推导替换为 `fileURLToPath`（只改克隆，不改主仓库）。
- 正在下载 E143 参考固件（`fetch-fw.mjs --model E143`，约 230MiB）；`port.mjs` 需要 E143 镜像做跨构建映射。

## 上游既有结论（docs/model-survey.md）

- E108 = E-P5 1.8：基址 0x7e101020，plain 资源，与 E143 配对 0.42M 条指令、188 个 lab 地址无法放置；状态 "not tried (base)"。
- E108 与 E100/E101/E106/E107/E110/E111/E112 同属**没有 0x9c100000 OSD 引擎**的一组；显示合成路径与已移植机型不同，是 GUI 仿真的主要硬件缺口。
- 所有 32 个机型共用同一容器与 AM33 reset head；CPU 仿真本身（MN10300/AM33）对 E-P5 适用。

## 里程碑 4：port.mjs 实跑与规则差异清单（进行中）

E143 参考固件已用 `fetch-fw.mjs --model E143` 下载并解包（230MiB，哈希校验通过）。`port.mjs E108` 逐个暴露 E-P5 与参考机型的结构差异；为拿到完整映射统计，在克隆内给下列规则加了 `OM_EP5_TOLERANT=1` 容错分支（**研究用，未验证，不代表这些事实已解决**）：

| 规则 | E-P5 上的差异 | 处理 |
|---|---|---|
| coreByte | 无独立 `movbu (abs32),d0; retf` 板字节 getter；SRAM 0x8ff00000 有 358 处引用，getter 形式不同 | 容错返回 null |
| resLoader | 索引读到 `0x605d6150`（+32 存 `0x605d6154`），无 E143 形式的 font/string 槽加载；资源按类型 0..17 分派（0x7e34a344 跳转表） | 容错返回空槽 |
| shootingService | "startShootingService start" 字符串被加载 2 次（规则要求 1 次） | 容错跳过 |
| dcfCounts | 无 E143 形式的 DCF 计数 getter | 容错返回 null |
| guiCanvas | 无 bank 0xb 设置（OSD bank 布局不同） | 容错返回 null，dram_size 置 null |
| expandImage/relocate | reset head 含拷往高段 flash 视图（0x7ef2d000/0x7ef4b000）的行，超出镜像范围 | 容错过滤镜像外行 |

MMIO census（`tools-ep5/probe-mmio.mjs`）：E-P5 命名 0x8ff00000（SRAM）、0x8fe00000（ISC，仅 8 处）、0x98x（串口/时钟）、0x99990000/0x99900000/0x99b00000（INTC 候选）、0x9a000000（450 处，外设主块）、0x9c000000（仅 18 处，VSC 候选）；**没有 0x9c100000 OSD 引擎**，与 survey 一致。E118 族 board 只是占位，寄存器布局需按 E-P5 自己的 census 重建。

资源加载器反汇编（objdump，CPU 0x7e34a314 起）：`mov 0x427c0000,a0; mov 2048,d0; mov 257,d1; call 0x7e34ab42` 读索引，返回指针存 0x605d6150；随后按类型分派到 0x7e34a528/0x7e34a5e5/… 各加载函数。字体/字符串槽的实际目的地址待从这些函数读出。

## 阻塞点与下一步（待本次运行更新）

1. port.mjs 映射统计完成后，记录配对/未放置数量与首个会话级阻塞。
2. 依失败点决定：为 E-P5 写专用 facts 规则/overrides，还是先做有界 GUI 探针（复用本项目 `tools/native_probe.py` 的固定 CPU 模型）。
3. 显示路径：E-P5 无独立 OSD 引擎，需要从固件反汇编确认其 GUI 合成/输出寄存器，才能谈“画出菜单”。

（本文随进展追加；不生成可刷固件，不访问相机。）
