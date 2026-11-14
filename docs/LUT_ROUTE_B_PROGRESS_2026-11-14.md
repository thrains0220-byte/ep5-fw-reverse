# 路线 B（机内 3D LUT）推进记录：D 诊断分支

日期：2026-11-14。目标仍是 E-P5 全幅 JPEG 首次编码前的 17³ 3D LUT、亮度/色彩变换与可换 SD 风格；本记录只描述本轮从 S4/S5 阻塞继续推进的证据。

## 已有基础（复用，不重造）

- `firmware/look_store.c`：`EP5IDX02`/`EP5LUT01` 解析、CRC、双表 staging/active 原子切换、槽位绑定。
- `firmware/lut.c`：17³ RGB16 三线性采样（红轴最快）。
- `firmware/film.c`：BT.601 全范围 YUYV 成对像素处理，恒等表逐字节不改，强度 0/128/256。
- `firmware/ep5_art_entry.S/.c`：四个原厂钩子（send/receive/JPEG/release）与 GCC↔MN103 ABI veneer。
- `tools.cave_entry.validate_look_runtime`：复用既有 CPU 模型，原 mode 3 全链路 9/9 已通过。

上游参考：Caduceus 的 17³/颜色引擎数据模型，Canon Soup Engine/M-Film 的卡上风格文件、后台分步处理与资源收尾原则。没有复制第三方固件地址、二进制或商业 LUT 文件。

## 本轮新增：D 诊断分支

诊断包编译时使用 `-DEP5_DIAG`：

- `ep5_art_before_jpeg` 只读取真实 JPEG request（buffer 地址、宽高、存储宽高、格式字节、16B 样本），不写像素。
- 不执行 LUT 加载，不中性化 ART packet，不申请 LUT pool；原厂成像路径照常运行。
- `ep5_art_before_release` 在安全点用已映射的原厂 write veneer 写 `EP5LUT/DIAG.LOG`。
- 诊断模块 ELF 中不含 `_ep5_film_apply`、`_ep5_look_load`、`_ep5_lut_sample16`；代码区只占 3,124B，`.bss` 1,036B 由构建器补齐到平面镜像并在首个 param send 清零。

文件服务逆向见 [FILE_SERVICE_MAP.md](FILE_SERVICE_MAP.md)：write 入口 `0x7e29159b`、消息号 `0x10003`、ret `[d2,d3,a2,a3],40`，与 read veneer 同构；直接后端 `0x7e296798` 的写分支证据已记录。

观测记录固定 128B，见 [DIAG_LOG_FORMAT.md](DIAG_LOG_FORMAT.md)。

## 离线验证结果

`tools/validate_diag_runtime.py` 在固定 MN103 模型上 3/3 通过：

| 场景 | packet 中性化 | 像素变化 | LUT pool alloc/free | DIAG.LOG | 文件后端 |
|---|---:|---:|---:|---:|---|
| observe | 0 | 0 | 0/0 | 128B | direct |
| observe_msg | 0 | 0 | 0/0 | 128B | message |
| write_fail | 0 | 0 | 0/0 | 0B（失败不提交） | direct |

两种文件后端日志字节一致，像素输出 SHA 一致。`tests.test_diag_log` 2/2 通过；Windows Caduceus 转换器单测 6/6 通过。WSL 运行 Caduceus 单测因环境没有 NumPy，不计为业务失败；已在 Windows Python 3.11 复跑通过。

## 诊断候选包

**2026-11-14 后续审查：以下旧包已撤回，不得刷入。** 它的地址可读性判断过宽，并且多次刷新覆盖之前记录。已修正源码并对新模块做离线测试，尚未重新生成候选包；写卡上下文、目录及耗时仍未在真机确认。详见 [日志格式与限制](DIAG_LOG_FORMAT.md)。

- 路径：`build/ep5-diag-card-01/DCOLYMP/E1089999.BIN`
- SHA-256：`85663965b4337c7b1dfe2cb7c97ae0b75984e0cea9bdafeaeb4a0ecc0740d0f1`
- 官方整包同尺寸：44,826,624B。
- 类型：`hardware-diagnostic`，**不是功能性 LUT 固件**，不承诺改变色彩。
- 目的：在真实 E-P5 上拍 1–3 张原厂照片，读取 `EP5LUT/DIAG.LOG`，取得 S4 的真实 buffer/geometry/format/sample 与 S5 的生命周期线索。

## 真机取证步骤

1. 先确认官方 1.8 或已验证 safe-7 可正常启动；诊断包不会改像素，但仍修改 cave/hooks，必须保留官方恢复卡。
2. 将 `E1089999.BIN` 放入卡根 `DCOLYMP/`，按 E-P5 已验证的 OK 开机更新流程刷入。
3. 正常进入菜单后，用 P/Natural、ART 针孔 I 各拍一张 4:3 最大 JPEG+RAW。诊断分支不改变画面；它只在 JPEG 钩子记录请求。
4. 接 USB 选 Storage，读取 `EP5LUT/DIAG.LOG`。若目录未自动创建或写失败，保留照片和错误状态；不要在拍摄时拔卡。
5. 用 `python tools/read_diag_log.py DIAG.LOG` 解码，并把同次 JPEG/ORF 文件名、尺寸、EXIF、日志一起归档。

## S4/S5 仍未完成的项目

诊断日志能证明 CPU 钩子看到的请求字段，但不能单独证明：

- ISP 输出的实际字节序/色域/量化范围；
- DMA cache flush/invalidate 和 JPEG 编码器的所有权切换；
- 全幅 15.9MP 的最坏耗时、看门狗让出、取消和连续拍摄资源寿命。

因此功能性 LUT 候选仍保持禁止。取回真机日志后，按 S4→S5 更新契约，再编译**独立**的 mode 3 功能候选；诊断包绝不重命名为功能包。
