# E-P5 LUT 项目进度核查（2026-11-13）

这是一份对当前工作区的核查，不是新固件发布说明。后续唯一执行主线见 [详细推进与交接计划](../plans/EP5_LUT_DELIVERY_PLAN.md)。旧聊天中尚未通过验证的“找到根因”“模式改成 8 即可”等说法不能作为实施依据。

## 本轮更新（2026-11-13 晚，mode 3 像素闭环打通）

本节取代下方“mode 3 失败”的旧结论。相机仍官方 1.8、USB 断开，本轮没有连接或刷写相机。

**已修复并验证：**

1. `ep5_art_after_wait` 现在接受 `enabled==3`，且 mode 3 仅在 `ep5_look_state[0]`（active 表）与 `[2]`（强度）非零时才置 `ep5_ready`，把资格绑定到本次真正加载成功的 SD look；失败/原厂回退不会改像素。
2. 运行时探针补上“原厂发送后计算几何”这一步：param send 时原厂先把 packet+80..91 清零，ART 消费者稍后才写回六个 u16 几何（见 NATIVE_CONTRACTS / CAVE_ENTRY）。探针此前缺这一步，JPEG 读到宽高=0 导致像素不变。现在按夹具 4×20 写回 packet+80，模拟原厂输出。
3. `validate_look_runtime` 两处既有测试 bug 修正：`card(**kw)` 不再丢弃 amount（half 用例强度真正生效）；`dict(**native)` 不再重复 name 键。池断言改为“无活块泄漏”为核心不变量，pool_fail 允许 alloc/free 计数不等。

**验证结果（WSL，固定 CPU 模型与官方 MAIN）：**

- `validate_look_runtime` 全部 **9/9** mode 3 用例通过：apply/half 像素改变且与宿主 C 参考逐字节匹配；missing_card/missing_lut/bad_index_crc/bad_lut_crc/zero_amount/pool_fail/wrong_slot 正确回退（像素不变、neutralized=0、无池泄漏、guard 保留）。
- 核心回归 `test_cave_entry / test_look_store / test_film / test_lut / test_mn103_lut` **32/32** 通过（含 callconv 夹具、全分辨率、host 对照）。
- Windows 桌面 `test_studio_* / test_film_update / test_trial_kit / test_prepare_trial_card` **48/48** 通过（临时目录须设在工作区内，沙箱 Temp 的原子 rename 会被拒，属环境限制非业务失败）。
- `EP5LUTStudio.exe` 已构建（build/lut-studio-dist/EP5LUTStudio/）。

**仍阻塞（防砖硬门槛，未绕过）：** mode 3 现为 `model-verified`。S4 静态像素契约（真实基址/容量/stride、RAW→YC 完成到 JPEG 读源串接、静态 ISP 字节序/范围/矩阵/色度采样、完成时点）与 S5 缓存/资源寿命**无法纯离线闭环**，计划禁止在此前生成功能性硬件候选。下一步只能走独立 D 诊断分支取证，或继续不依赖真机的 S7 桌面交付。旧 RC2 真机证据不覆盖新 SD LUT 运行时。

## 当前结论

- 相机：按机主最后确认及已存证据，已从固定柔彩 RC2 正常恢复官方 1.8，USB 已断开。本次没有连接、操作或刷写相机。
- 固定柔彩 RC2：已有单台 E-P5 启动、菜单、全尺寸 RAW+JPEG、同源 RAW 重显影和正常官方恢复的证据。它修改原生色度曲线，**不等于任意 3D LUT 直出**。
- LUT Studio：已有可运行的 Windows EXE，可管理 `.cube`、预览、调强度、保存项目和拟分配 ART 槽。导出仍是 `camera_ready=false` 的开发数据包。
- 通用 SD LUT 固件：尚未打通。当前 mode 3 集成探针首个 `apply` 案例失败，没有新的可刷通用 LUT 固件。
- 画质：全尺寸未压缩缓冲和首次 JPEG 编码前接入是目标及局部原厂模型证据；真实照片的像素编码、缓存、时序、耗时和最终画质尚未完成通用 LUT 验证。

## 本次实际复跑

验证期间相关源码 SHA-256 保持不变。测试结果及输入哈希保存在 [机器可读记录](lut-progress-audit-20261113.json)。本机完整日志位于 `build/progress-audit-20261113-review/`，该目录不随 Git 分发；机器可读记录保留关键结果和失败摘要。

| 验证项 | 本次结果 | 能证明的范围 |
| --- | --- | --- |
| Windows `test_studio_*.py` | 24/24，通过，无跳过 | 导入、预览、项目、导出、Tk 回调等桌面行为 |
| 现有 `EP5LUTStudio.exe --smoke-test` | 通过 | 现有 EXE 启动并渲染；不证明二进制与今后源码一致 |
| 宿主 C `test_look_store.py` | 7/7，通过，无跳过 | 真实桌面协议字节的独立 C 加载、CRC、混包及失败路径 |
| `test_cave_entry.py` | 4/4，通过，无跳过 | 包括 29 个旧 LUT/资格模型案例、14 个单字段参数案例及布局/基线拒绝；不覆盖 mode 3 成功链 |
| `test_mn103_lut.py` | 3/3，通过，无跳过 | MN103 核心与宿主参考及边界、取消夹具；不证明机身 ABI/性能 |
| 原厂文件与槽选择器审计 | 6 个文件 API 案例、39 组选择器输入通过 | 文件封装与直接/消息后端、模式选择；文件系统与队列仍为模型 |
| 原厂像素与内存池审计 | 通过 | 两条绘图路径各 9 色、针孔请求构造、池申请成功/失败/释放；静态照片编码与真实剩余内存仍未证明 |
| `validate_look_runtime`（mode 3） | **失败** | 第一个 `apply` 未走完参数阶段，不能计为任一成功案例 |

上表共有 38 项 unittest 通过；原厂审计案例和 EXE smoke 另外列出，不能混成“已完成多少项机身功能”。本轮没有运行全仓所有测试，旧 RC2 真机证据也没有重新拍摄。

mode 3 本次失败摘要：

```text
RuntimeError: Command failed: ... ep5-look-runtime-probe ... 'apply' ...
param phase failed stop=1 preserved=0 envelope=0 sends=1 sp=6000efd8
```

## 已确认的阻塞和交接陷阱

1. **测试后端本身不可靠。** 新探针的若干 HLE 分支 `return 1` 却不推进 PC；发送钩子提前停止，绕开正常返回和 veneer 的恢复代码。必须先使后端返回语义与原调用帧一致，不能靠改预期寄存器、写回返回地址或强制停止“修绿”。
2. **mode 3 尚不能取得正常资格。** `ep5_art_after_wait` 只接受 `enabled==1`，JPEG 入口却要求 mode 3 已有 `ep5_ready`；mode 3 释放也未清理这两个资格字。即使修好池分配，成功套表仍然被挡住。
3. **新的运行时夹具覆盖了图像尺寸。** `validate_look_runtime` 把 config +28/+32 的几何改写成 PictureMode/variant，C 探针又把同一 8 字节拷到 JPEG 几何全局，不能再称为 4×20 像素的正确链路。
4. **半强度与零强度测试尚不能测到声明的输入。** Python 构卡时删掉了 `amount` 参数，所有索引实际上仍使用默认 256。另有 `dict(name=name, **native, ...)` 与 native 已有 `name` 的重复关键字，执行到该处还会失败。
5. **ABI 不能沿用前面试错的解释。** 新 `.S` 文件/池适配器未通过端到端验证。现有独立原厂池探针在 **mode 3** 成功；没有证据要求改成 mode 8。必须分别验证 GCC 参数位置、厂商寄存器/栈参数、返回值及非易失寄存器。
6. **最小调用探针是假阳性风险。** `callconv_probe.c` 只要打印过入口就返回成功，未要求无 abort 且返回终点；它不能作为 ABI 验证通过的凭据。
7. **两张表空间多分配了一倍。** 一张 17³ RGB16 表为 29,478 字节，两张需要 58,956 字节；当前 mode 3 申请 117,912 字节。需审查申请、两表偏移和容量，而非仅改一个常量。池失败次数也不能被当成成功分配数要求一一释放。
8. **失败回退未形成完整契约。** 已中性化 packet 后，等待/JPEG/取消阶段失败，仅“跳过 LUT”不一定得到原厂 ART 效果。必须保留或重建原路径，不能保存半处理帧或静默输出错误风格。
9. **多槽和画质还缺生产契约。** 桌面的 14 个拟用槽都标着 `runtime_verified=false`；某些槽不走现有 ART 任务列表。固定 token/context/地址可复用，不足以排除跨拍摄旧回复；缓存、DMA、卡根路径和文件任务也未证明。
10. **说明与当前源码有脱节。** `CAVE_ENTRY.md` 仍写旧的 6 字控制、8 字状态和内置 LUT；当前构建是 7 字控制、24 字状态、外置 LUT。旧计划的未打勾状态、旧任务分工和历史验证 JSON 不能覆盖本次核查。

## 必须保留的基线事实

| 项目 | 当前核对值 |
| --- | --- |
| 本地分支 / HEAD | `work/ep5-film` / `09ec3e6d78aae727ced636340f5e3ac00caafa0c` |
| 官方 1.8 解码 MAIN SHA-256 | `dfe255e4d5a43329712c1fdfd6861ee1f3ef54a268b6096628bf045d8cc590df` |
| CPU 模型固定提交 | `6adb3bef36239859ae3fcd94b0dbb7db6de6ffa1`（只复用 CPU 实现，不复用别机型地址） |
| 编译器 | `mn10300-elf-gcc (GCC) 14.3.0` |
| 候选代码区 | `[0x7e128010, 0x7e130000)`，32,752 字节；加载/执行仍需验证 |
| 本次模块 | 4,444 字节，默认关闭，`installable=false`，不是更新 BIN |
| 本次模块 SHA-256 | `4d3f1763112074d161d5e6caf5ac41b0a0d437823a9496eff0609f9e4e518c72` |
| 控制 / 状态 | 28 / 24 字节；偏移只从当次 manifest/符号取得 |
| SD 协议 | 索引 `EP5IDX02` v2；LUT `EP5LUT01`，17³ RGB16LE、红轴最快 |

4,444 + 29,478 = 33,922，比现有代码候选区大 1,170 字节。因此不能在当前模块后直接拼上一张默认完整 LUT。首用内置风格的生成、压缩或原生参数方案，需要单独核算和验证。

大量新模块和测试仍未提交。其他人只克隆 GitHub 未必能取得这些成果；接手前必须保全工作区并形成可恢复的源码快照。本次尝试读取远端分支头时 GitHub 连接被重置，未确认远端最新提交，也没有推送任何改动。

## 已有真机证据的边界

参考 [RC2 成片](rc2-first-trial.json) 与 [官方恢复](rc2-recovery-verification.json)：同一 `0080.ORF` 保持原哈希；恢复后的机内重显影与刷前 **解码 RGB** 相同，整份 JPEG 文件并非逐字节相同。正常回刷成功不等于断电后或更新器无法启动时也可恢复。

本轮产物是这份核查、验证记录与后续计划。没有继续修改固件实现，也没有制造一份声称可用的新升级文件。
