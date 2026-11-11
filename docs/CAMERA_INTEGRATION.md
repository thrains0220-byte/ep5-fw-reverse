# 实机接入准备

目标仍是 E-P5 机内保留 ORF、生成全尺寸胶片风格 JPEG。本轮交付可编译、可执行验证的处理引擎和连接后可直接运行的资料采集工具；尚未交付机身加载器或固件更新包。连接相机后是否只需小改，取决于下面尚未确认的硬件条件。

## USB 数据线到手：只读导入原片

第一轮拍样、接线、导入与后续刷写门槛的连续步骤见[接入清单](CONNECT_DAY.md)。

[E-P5 官方说明书第 101–102 页](https://download.omsystem.com/pages/inst/ep5/manual_ep5_ENU.pdf)要求连接后在机身选择 **Storage**；它是文件传输模式，连接期间不能在机身拍摄。先在未连接时拍 4:3 最大尺寸 RAW+JPEG 的固定场景并保留原卡，再接线、选择 Storage，找出电脑挂载的含 `DCIM` 的目录。不要把 USB Storage 当成运行中固件调试接口。

从卡上明确指定同次 ORF/JPEG 文件名，例如：

```bash
python3 tools/usb_collect.py --source /media/USER/CAMERA --out sessions/first-usb \
  --file /DCIM/100OLYMP/P1010001.ORF \
  --file /DCIM/100OLYMP/P1010001.JPG
```

把 `/media/USER/CAMERA` 和实际文件名换成电脑显示的路径。工具只读这些文件，拒绝软链接、越界路径、超 128 MiB 文件和输出目录落在相机挂载目录内；复制到新建的私有会话目录，记录 SHA-256/字节数、JPEG 头尺寸和完成状态。它检查文件头，**不等于**完整 ORF 解码或 JPEG 图像验证。若需比较同一 ORF 的机内 RAW 编辑输出，在断开 Storage 后操作相机，再重连并把生成的 JPEG 作为另一次 `--file` 加入新会话。断开连接前按系统流程卸载介质。

## 已实现的处理入口

`firmware/film.h` 提供两个入口：

- `ep5_image_from_desc(out, desc, desc_bytes, mapped_address, memory, capacity)`：从至少 32 字节的小端原厂格式描述符生成有界图像视图。描述符中的地址只用于计算偏移，绝不直接当作 C 指针解引用。必须另行取得实际可访问映射及长度。
- `ep5_film_apply(image, lut, values, encoding, amount, progress, context)`：在原始尺寸的图像缓冲区内处理，不分配整幅 RGB 图。`amount` 为 0..256；LUT 是 17³ RGB16、红轴最快，共 29,478 字节。行间填充不变。

当前唯一候选编码为显式传入的 `EP5_BT601_FULL_YUYV`：全范围 BT.601，字节顺序 Y0/Cb/Y1/Cr。它来自同代机型的可行路线和通用颜色变换，**不是 E-P5 已实测的像素编码**。真实缓冲区不符合时必须增加对应适配，不能只把编码标志设为 1。

处理顺序是 YCC→16 位 RGB→LUT→颜色差值→原始 YCC 加差值；两个像素的色差变化取平均。保留原始 YCC 残差，避免恒等 LUT 因重建 RGB 时的色域裁切损坏饱和颜色。内部 16 位计算不会增加原始 8 位缓冲区的信息，也不等同于直接处理 RAW。当前没有颗粒或光晕，以免在未校色前改变细节。

`progress(context, completed_rows, total_rows)` 在开始前及每最多 16 行调用；回调返回非零继续，返回零取消。机身适配层需在这个位置调用经过验证的让出调度/看门狗服务，不能直接套用别的机型地址。回调不能修改图像描述符、LUT 或缓冲区所有权。

| 返回值 | 原厂调用方必须如何处理 |
| --- | --- |
| `0` | 处理完成；只有所有权、缓存及原厂任务条件也满足时才允许编码 |
| `EP5_FILM_INVALID (-1)` | 参数无效，处理入口未改像素；禁用本次效果并报告原因 |
| `EP5_FILM_CANCELLED (-2)` | 在处理前取消，图像未改动 |
| `EP5_FILM_DISCARD (-3)` | 已处理部分行；必须丢弃工作图并从保留的 RAW 重新显影，禁止编码或重复套用 LUT |

图像、LUT、描述符输出和回调状态须互不重叠，调用期间由同一处理任务独占。代码不访问 ORF、SD 或 JPEG 文件，因此也不能凭核心测试断言整机一定保留 ORF。

## 原厂描述符已验证到哪里

原版 1.8 的 `0x7e40fba4` 是描述符调试输出例程，原厂调用帧为 `[a2],8`。`tools/image_probe.py` 执行其原始指令，只把两个日志输出函数替换成有明确返回帧的记录器；输入描述符只读，写入仅允许合成栈。

| 偏移 | 字段 | 长度 |
| --- | --- | --- |
| 0 / 4 | pAddress / pAddressC | 各 4 字节 |
| 8 / 10 | usDataFormat / usMemHw | 各 2 字节 |
| 12 / 14 | usUseHw / usUseVw | 各 2 字节 |
| 16 / 18 | usAreaHw / usAreaVw | 各 2 字节 |
| 20 / 22 | usOffsetH / usOffsetV | 各 2 字节 |
| 24 / 26 | usCenterH / usCenterV | 各 2 字节 |
| 28 | dummy | 4 字节 |

每个字段填入不同值，核对实际日志的名称和值；同时核对被调用方应保留的寄存器和栈。这个结果证明该描述符读取函数及调用帧，**不证明哪一个拍摄任务持有全尺寸有效图像**。

当前适配器仅接受 `DataFormat=0x302`、`pAddressC=0`、偶数宽度及偶数水平起点，要求裁切后的每一行全部落在独立提供的映射内。拒绝单独色差平面及其他格式，避免误解释真实数据。

## 相机连接后的第一条命令

电脑手动加入相机自身 Wi-Fi 后，在仓库根目录运行：

```bash
python3 tools/camera_collect.py --out sessions/first-connection
```

它先请求 `get_caminfo.cgi`，确认 E-P5 身份后再读取能力、当前连接模式和 `/DCIM` 列表。使用系统 Python 标准库；不切换网络、不使用环境代理、不跟随 HTTP 重定向、不发送拍摄或写入命令。默认主机为 `192.168.0.10`，可通过 `--host` 指定局域网 IPv4。caminfo 只接受 UTF-8/ASCII，拒绝 DTD、实体声明及 NUL。

一次请求最长 30 秒，套接字空闲超时 8 秒；元数据最多 512 KiB，单张原图最多 128 MiB。输出目录必须不存在，目录/文件权限为 0700/0600；包含原始响应、SHA-256、长度和完成/中断状态。失败立即停止，保留已有资料及可能的 `.part`，不能把不完整会话当作完成。

依据真实列表中的路径，可在新的会话目录请求原图：

```bash
python3 tools/camera_collect.py --out sessions/reference-pair \
  --file /DCIM/100OLYMP/P1010001.ORF \
  --file /DCIM/100OLYMP/P1010001.JPG
```

上述文件名只是示例，程序不会猜测或触发拍摄。只接受明确的 DCIM/目录/ORF 或 JPG 路径；ORF 检查签名，JPEG 读取帧尺寸，不调用缩图接口。这些结构检查不是完整的 RAW/JPEG 解码或端到端源文件校验。目录中可能有机身序列号和私人照片，`sessions/` 已从 Git 忽略。

## 实机阶段仍需解决的条件

1. **诊断与代码加载入口。** 正常 Wi-Fi HTTP 成功只代表能读取资料，不能据此上传代码、读 RAM 或执行处理核心。SD 参数实验也还未在整机上验证；若需要放文件，仍需 USB/读卡器等可写入方式。不能承诺只连接普通 Wi-Fi 就能自动完成刷机。
2. **完整拍摄调用链。** E-P5 的 `0x7e3f4884` 是 `REC MISC YC2JPG` 候选，接收上下文 `a0` 和独立输入 `a1`；调用点如 `0x7e3f2a13` 使用 `[d2,d3,a2,a3],16`。该输入不是本页 32 字节通用描述符，不能直接交给适配器。需追踪完整显影→RAM→编码路线与完成信号，并决定 JPEG、缩略图、回放各处理一次的策略。
3. **内存、缓存与调度。** 找到不会被原厂覆盖的代码/LUT 区，确认当前任务栈、CPU 核、可编辑缓冲区寿命及缓存维护方式。不能借用 E-M10 的地址或把 CPU 模型中的合成地址刷进相机。
4. **画质与退出验收。** 用同次拍摄 ORF/原生 JPEG 检查矩阵、范围、色域、白平衡、尺寸与色阶，再校色；测试 RAW+JPEG、机内 RAW 显影、连续操作、取消、关机及恢复。机身加载失败时须能禁用效果并保留原厂保存路径。

这些条件没有被包装成“最后改几行配置”。本轮代码减少的是确定可以提前完成的软件工作；未取得运行中的机身证据前，不能保证最后一段接入的难度。

## 离线复现

先按 README 准备固定版本的官方输入、CPU 引擎和本地工具链，再运行：

```bash
python3 tools/image_probe.py data/ep5-decoded/00_0100_402c0020.decoded.bin \
  --out generated/ep5-image-descriptor.json
python3 tools/check_mn103_lut.py --film --out generated/ep5-film-mn103.json
python3 -m unittest discover -s tests -v
```

报告目标代码使用合成 GCC 调用者和地址。目标引擎测试程序为 2,567 字节，含测试调用者、进度回调及取指填充；它不是可刷固件或经过布局确认的机身常驻模块。真实插入点和编译方式确定后，大小会变化。
