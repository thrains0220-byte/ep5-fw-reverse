# 从 SD 选片到全尺寸照片

2026-11-21。32 款数据包在电脑上从同一张 E-P5 Natural JPEG 生成了 32 个不同的全尺寸结果。菜单、读卡、拍摄、色轮与颜色预览组件已经用 E-P5 的 MN103 工具链编译。已有真机记录覆盖固定柔彩 RC2 和机主验收过的固定七槽版本。通用 SD 版的相机菜单和实际拍摄仍待接入与验证。

## 这次拍摄测试实际经过哪里

1. 将原厂 Natural JPEG 解码一次，转换为 4608×3456 的全范围 Y0/Cb/Y1/Cr 测试帧。所有风格共享这同一输入。
2. 用 C 菜单控制器处理分组、列表、强度、确认、两次返回。用文件工作线程读所选组的索引、17³ RGB16 色表和纹理配方。预载与拍摄分别持有各自需要的状态。
3. 快门时核对卡、组、所选风格及其版本，锁定对应色表。拍摄核心可合成十二色区调整，再进行基础色调和纹理处理。零强度原样通过。错误色表回退，处理中途取消只释放资源，不输出半张图像。
4. 每款都处理完整 15,925,248 像素。保存 Gold、Portra、Velvia、CineStill、Atrophy 和森山风样片，并读回尺寸与 EXIF 配方。其余结果保存全帧哈希和缩略图。全尺寸同源对照与个人原片只保存在本机。

本次输入已经是 JPEG，只能评估这张照片的色彩、纹理与细节，原始高光余量、传感器色域和机身编码损失仍需用真实拍摄判断。三款黑白分别使用高、中、低的颗粒设定。FX2 为 Atrophy 增加局部清晰度，32 个输出与上一版逐一对比，只有 Atrophy 的全帧哈希改变。预览显示颜色和色轮变化，纹理在照片阶段处理。[本次逐款结果](ep5-personal32-fx2-receipt.json)

从已解压的卡目录显影时，菜单会自动读取当前组和菜单槽保存的十二色区设置。重新启动显影程序仍能取得相同像素。损坏或与色表身份不符的调整会被忽略。已取得有效原帧、尚未写入任何像素时，若色轮或纹理缺少工作内存，拍摄核心会交回完整原帧。中途取消则丢弃已改过的帧。

## 使用和复现

仓库 [looks 目录](../looks/) 提供 29 款和 32 款数据包，并保留此前的 FX 格式。下面的 Windows 命令使用 Python、NumPy、Pillow，以及带 C 编译器的 WSL。将 `natural.jpg` 换成自己的 sRGB 照片。重新跑对照时会在指定输出目录写入样片，宜使用独立目录。

```powershell
python tools/audit_sd_photo.py natural.jpg looks/EP5-Personal-32-FX2.zip build/my-comparison
Expand-Archive -LiteralPath looks/EP5-Personal-32-FX2.zip -DestinationPath build/example-card
python tools/render_sd_photo.py natural.jpg build/example-card Gold build/example-Gold.jpg
python tools/render_sd_photo.py natural.jpg build/example-card 森山黑白 build/example-BW.jpg --bank 3
```

Windows 使用者可以在 Studio v2 点「编辑 SD 卡包…」完成添加或替换。命令行同样可直接编辑仓库附带的 ZIP。输入应明确为显示 sRGB 到显示 sRGB 的归一化 3D LUT。电影 Log 转换表需要先匹配输入。以下依次列出全部槽位、给第三组空位加风格、仅替换第一组的第 12 项。每次另存到新 ZIP。[Windows 使用说明](STUDIO_V2_GUIDE.md)

```powershell
python tools/custom_sd_card.py --card looks/EP5-Personal-32-FX2.zip --list-slots
python tools/custom_sd_card.py build/My-looks.zip --card looks/EP5-Personal-32-FX2.zip --add-srgb-cube "旅拍=D:\LUT\Travel.cube"
python tools/custom_sd_card.py build/My-gold.zip --card looks/EP5-Personal-32-FX2.zip --replace-srgb-cube 1 12 "暖金=D:\LUT\WarmGold.cube"
```

目标构建在 WSL 运行 `python3 tools/check_photo_core.py`。18 个模块链接后的 `text` 段为 26,292 字节，无未解析符号。输出为可重定位的目标文件。目标机性能、原厂任务连接和液晶显示仍待验证。

## 距离机内直出

当前有两个具体的硬件缺口。真实 ART 界面还需要在菜单中将选组、重绘、半按快门及退出交给对应的原厂任务，排除之前的黑屏和无法关机。拍摄时还需要确认 ISP 完成写入、CPU 可以独占目标缓冲以及原厂 JPEG 编码开始读取的时刻。现有模型已找到全幅缓冲，原厂 CPU 绘图路径也有 YUYV 证据，但会话内没有这台相机的 ISP 原生像素转储或缓存交接记录。

拿到有明确来源的像素文件和同帧 JPEG 后，可用[同帧像素比对](EP5_CAPTURE_FRAME_COMPARE.md)核实字节排列、范围及颜色矩阵。这个检查不能判断 CPU 与 JPEG 编码器的缓存交接时刻。

这两处接通后，在第二组选择一个该组独有的名字，确认能退出、半按和关机。再用同一份 ORF 比较关闭、恒等、零强度和 Gold，实拍全尺寸 JPEG＋同号 ORF，核对四角、灰阶、强饱和色、写卡时间以及正常关机。目录里没有新可刷固件。操作与其余功能见[机身控件核查](EP5_CAMERA_CONTROLS.md)、[取景](EP5_COLOR_PREVIEW.md)、[色轮](EP5_WHEEL_EDITOR.md)和[纹理](EP5_FILM_FX.md)。
