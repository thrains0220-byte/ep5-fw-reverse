# E-P5 机内胶片模拟

目标：保留 ORF，在奥林巴斯 E-P5 内生成全分辨率胶片风格 JPEG，允许拍后等待。

**当前状态：研发中，尚未完成机内成片。** 已实现并测试色彩核心，独立核对原版固件，运行原版指令验证了 SD 参数的 CSV 解析、RAM 覆盖、读取、清除以及调试启动分支。相机未连接，尚未验证图像缓冲区、机内运行或成片色彩。

这是一个新项目，不依赖此前的 ep5-fw-reverse 仓库、ART 解锁补丁或地址结论。

## 已有内容

| 内容 | 状态 |
| --- | --- |
| OM 官方 E-P5 1.8 基线、四块校验、原样重打包 | 已在本机验证 |
| 主程序映射 `0x7e101020` | 大量字符串引用及原生启动指令相互印证；区别于更新包 flash 地址 |
| 17³ RGB16 LUT 编译器和无动态分配 C 核心 | 主机测试通过；LUT 为 29,478 字节 |
| 4608 × 3456 RGB8 图像处理 | 主机测试通过，恒等 LUT 逐字节一致；不是 ORF 显影测试 |
| 原版 CSV → RAM 参数覆盖 → 原版 Wi-Fi 开关分支 | 受限 CPU 模型中验证；文件系统、并发启动及无线硬件未验证 |
| E-P5 的原生 JPEG/Beauty/Bayer→YC 路径 | 已得到新的反汇编线索，尚未确立安全插入点 |
| 可刷胶片模拟固件、相机加载器、真实样片 | 尚未实现 |

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

## 下一步实机入口

[SD 参数诊断实验](experiments/01-wifi-shell/README.md)提供一个候选入口：让相机原生导入 `F971=1`，观察是否启动 Wi-Fi 诊断服务。文件中没有程序或固件镜像。E-P5 的解析与开关已经离线验证，**整机启动和无线连接仍待实机验证**。

没有读卡器时，可先核对[原生 Wi-Fi 读取入口](docs/WIFI_READONLY.md)，获取机身信息并验证原图下载；这条路径尚不能把诊断文件写入 SD。

相机当前安装的是来源未完全确认的历史修改版；它与上述精确原版基线不等同。最终补丁必须针对确定的原始镜像构建，不能对未知修改版推测偏移。

## 还需完成

1. 实机确认诊断入口，取得当前运行状态和必要的缓冲区信息。
2. 确认编码前的全尺寸缓冲区格式、范围、色彩空间、生命周期及缓存同步。
3. 确认可执行代码驻留区、调用约定和禁用路径，再把色彩核心接入。
4. 用 E-P5 自己的 ORF/原生 JPEG 成对校色，检验细节、色阶、压缩与异常退出。

主机 RGB 核心不是机内移植的替代品。当前不会产出以 `E1089999.BIN` 命名的实验固件。

详细证据见 [研究记录](docs/FINDINGS.md)，后续检查项见 [实施记录](docs/superpowers/plans/2026-11-10-ep5-film.md)。
