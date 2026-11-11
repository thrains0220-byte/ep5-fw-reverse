# E-P5 机内胶片模拟

目标：保留 ORF，在奥林巴斯 E-P5 内生成全分辨率胶片风格 JPEG，允许拍后等待。

**最终交付物是可在 E-P5 安装并启用效果的固件升级文件。** 具体使用体验、开源参考取舍及完成验收见[固件交付目标](docs/FLASHABLE_PRODUCT.md)；工具和算法核心都是中间成果。

**当前有一个 E-P5 1.8 完整升级包候选。** 「柔彩」通过原厂两条色度 LUT 调整 ART → 针孔相机 I 的静态照片。已生成 44,826,624 字节的 `DCOLYMP/E1089999.BIN`，完成四块校验和原厂模式选择指令对照。尚未在机身确认启动、成片或恢复。哈希、用法与重建命令见[柔彩候选 1 使用说明](docs/SOFT_CHROME.md)。

仓库同时保留独立的软件 17³ LUT 移植实验。该引擎仍在验证像素格式、缓存与调度。

这是一个新项目，不依赖此前的 ep5-fw-reverse 仓库、ART 解锁补丁或地址结论。

## 已有内容

| 内容 | 状态 |
| --- | --- |
| OM 官方 E-P5 1.8 基线、四块校验、原样重打包 | 已在本机验证 |
| 主程序映射 `0x7e101020` | 大量字符串引用及原生启动指令相互印证；区别于更新包 flash 地址 |
| 17³ RGB16 LUT 编译器和无动态分配 C 核心 | 主机及 MN103 指令模型测试通过；LUT 为 29,478 字节 |
| YUYV 候选适配、16 位采样、强度/进度/取消 | 已实现；显式 BT.601 全范围假设，尚未实测 E-P5 编码 |
| 原厂 32 字节描述符读取与裁切范围验证 | 原始读取指令及函数调用帧通过模型测试；不证明真实缓冲区归属 |
| 4608 × 3456 RGB8 图像处理 | 主机测试通过，恒等 LUT 逐字节一致；不是 ORF 显影测试 |
| GCC 14.3.0 / MN103 编译与执行 | RGB8 7 例、YUYV/描述符/取消 17 例与主机比对；当前测试代码分别为 853 / 2,567 字节 |
| 连接后只读资料采集、指定 ORF/JPEG 下载 | 工具及本地 HTTP 测试完成；尚未连接相机 |
| 原版 CSV → RAM 参数覆盖 → 原版 Wi-Fi 开关分支 | 受限 CPU 模型中验证；文件系统、并发启动及无线硬件未验证 |
| E-P5 原厂 ART→JPEG 输入构造 | 40 字节输入、原始指令及调用帧已离线核对；像素生产、普通拍摄路由与安全插入仍待解决 |
| ART 调用→候选空间内色彩模块→原厂 JPEG 调用 | 实际目标指令链已在模型中连通；含 LUT/资格状态与参数实验共 31,886 字节，默认关闭，尚非可安装固件 |
| 原厂启动读请求、全尺寸分配与中性 ART 列表 | 原始指令验证覆盖候选区域、申请 4608×3456×2、可省去附加滤镜；实际装载/ISP/调度仍待验证 |
| 完成回复资格、单次处理及释放清理 | 三处固件桥与29目标案例已实现；跨任务回复新鲜度、缓存及实机仍待验证 |
| 原厂色度 LUT 升级包 | 柔彩候选 1 已生成，真机安装与样片待验证 |

## 使用与复现

Python 3.10+、C 编译器和 Git 即可运行色彩核心及其测试。原生 CPU 探针需要下面固定版本的外部源码；纯色彩处理不依赖它们。

```bash
python3 -m unittest discover -s tests -p test_lut.py -v
python3 tools/compile_lut.py --out build/warm-negative.rgb16le
python3 tools/compile_lut.py your-look.cube --out build/your-look.rgb16le
```

不带输入时生成原创实验风格 Warm Negative，**尚未按 E-P5 样片校色，也不声称复刻某种胶片**。导入仅接受 `LUT_3D_SIZE 17`、归一化 `[0,1]` 域和有限 `[0,1]` 输出，拒绝静默裁剪。红色轴变化最快。生成的数据目前不能直接放进相机使用。

```bash
git clone https://github.com/fishcu/oly_fw_analysis.git external/oly_fw_analysis
git -C external/oly_fw_analysis checkout a61498eecba1125010956864acbefaa1e4ff5f9e
git clone https://github.com/cmdada/em10-fw.git external/em10-fw
git -C external/em10-fw checkout 6adb3bef36239859ae3fcd94b0dbb7db6de6ffa1

python3 external/oly_fw_analysis/tools/om_firmware_catalog.py \
  --model-id 1080 --model-name E-P5 --out data/ep5-stock --download
python3 external/oly_fw_analysis/tools/oly_container.py \
  data/ep5-stock/OLY_E_108_1800_0000_0000.BIN --out data/ep5-decoded \
  --expect-sha256 cc59a4e13b3bf6c46405bd396975cb9c93a7634b7a4a36822259b1fc498b5cfd
python3 tools/inspect_ep5.py data/ep5-stock/OLY_E_108_1800_0000_0000.BIN \
  --out generated/ep5-inventory.json
python3 tools/native_probe.py data/ep5-decoded/00_0100_402c0020.decoded.bin \
  --out generated/ep5-native-current.json
python3 -m unittest discover -s tests -v
```

下载和报告输出目录/文件须尚不存在。已完成设置的当前工作区可直接运行最后一条测试命令。工具不访问相机、不刷机。完整官方镜像和解包数据仅保存在忽略的 `data/` 中。

本机已构建 MN103 GCC。编译色彩核心、执行真实目标指令并生成比对报告：

```bash
python3 tools/check_mn103_lut.py --out generated/ep5-lut-mn103.json
python3 tools/check_mn103_lut.py --film --out generated/ep5-film-mn103.json
```

工具链复现细节见 [MN103 构建记录](docs/MN103_TOOLCHAIN.md)。目标验证使用合成内存和 GCC 调用者；没有模拟像素算法服务，没有接入原版固件调用约定。生成的 `lut.bin` 是模型中的测试程序，不能作为相机更新文件使用。

处理接口、取消结果、连接后的第一条命令及接入条件见[实机接入准备](docs/CAMERA_INTEGRATION.md)。完整测试还覆盖 4608×3456 YUYV 图像的原地处理及行填充保护。

## 下一步实机入口

[SD 参数诊断实验](experiments/01-wifi-shell/README.md)提供一个候选入口：让相机原生导入 `F971=1`，观察是否启动 Wi-Fi 诊断服务。文件中没有程序或固件镜像。E-P5 的解析与开关已经离线验证，**整机启动和无线连接仍待实机验证**。

没有读卡器时，可先核对[原生 Wi-Fi 读取入口](docs/WIFI_READONLY.md)，获取机身信息并验证原图下载；这条路径尚不能把诊断文件写入 SD。

电脑已加入相机网络后，可直接运行 `python3 tools/camera_collect.py --out sessions/first-connection`；程序不自动连接无线网络，首次联网仍需用户手动完成。

数据线到手后，在相机 USB 菜单选择 Storage，按[第一轮接入步骤](docs/CONNECT_DAY.md)拍样并用 `tools/usb_collect.py` 只读导入指定 ORF/JPEG。Storage 期间相机不能拍摄，USB 文件传输不能替代运行中固件调试。

用户确认机身显示 1.8，现有镜像的具体来源尚未核实。本候选从已核对哈希的官方 1.8 完整包构建。如果机身装有旧改版，安装候选会替换原有改动。

## 软件 17³ LUT 路线还需完成

1. 实机确认诊断入口，取得当前运行状态和必要的缓冲区信息。
2. 确认编码前的全尺寸缓冲区格式、范围、色彩空间、生命周期及缓存同步。
3. 确认可执行代码驻留区、调用约定和禁用路径，再把色彩核心接入。
4. 用 E-P5 自己的 ORF/原生 JPEG 成对校色，检验细节、色阶、压缩与异常退出。

该软件 LUT 路线的模型模块不能作为升级文件使用。原厂色度 LUT 候选由 `tools/build_native_film.py` 从官方 1.8 原版构建。

详细证据见 [研究记录](docs/FINDINGS.md)，后续检查项见 [实施记录](docs/superpowers/plans/2026-11-10-ep5-film.md)。

新增参考检查：[OM-C dbv0.4.0](docs/OM_C_DBV040_REVIEW.md)。其 E-P5 1.8 光圈环候选的字节约束和整包输出已独立复现；提供了 32,752 字节代码/数据布局候选，尚不是胶片功能或运行期空闲证明。

基于该位置继续实现的 [E-P5 胶片模块候选](docs/CAVE_ENTRY.md)包含原厂 ABI 跳板、已有色彩核心、一个 LUT 和有界适配器。它只输出模型模块与验证记录，不输出相机升级文件。

后续[原厂装载与 ART 生产者检查](docs/NATIVE_CONTRACTS.md)已从预置几何的 JPEG 构造，推进到原厂尺寸表与分配结果的传递，并找到了保留 RAW→YC、去掉附加艺术滤镜的列表构造候选。
