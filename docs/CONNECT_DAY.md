# E-P5 数据线到手后的第一轮接入

目标是先取得可复核的机身原图和当前版本，再决定能否开始固件实验。USB Storage 只提供文件访问；[E-P5 官方说明书第 101–102 页](https://download.omsystem.com/pages/inst/ep5/manual_ep5_ENU.pdf)要求选择 **Storage**，连接时不能继续在机身拍摄。它不是运行中固件控制台。

2026-11-13 已在 Windows 上实测 **MTP** 读取原始 JPG／ORF，两次下载一致且完整解码通过。Windows 用户优先按[MTP 取样说明](MTP_READONLY.md)使用 `tools/mtp_collect.py`；无需为了采集照片改用下面的 POSIX Storage 工具。机身菜单为 1.8，MTP 的 1.00 是已核对的原厂固定字段。[本轮记录](mtp-first-connection.json)和[原厂 USB 静态证据](USB_STATIC.md)均未宣告固件效果或运行时内存调试已完成。

## 1. 未连接时留样

在机身记录版本页面与此前改版的已知情况。设 4:3、最大尺寸、RAW+JPEG、固定白平衡与曝光，拍一张同时有灰、红、绿、蓝、亮部和暗部的静物，再拍肤色、日光和室内场景。保留各张 ORF 和原生 JPEG 的文件号；先导入这组基线文件，再断开 USB。在回放 RAW 编辑中对**同一 ORF**分别生成一张中性和一张原厂风格 JPEG，记下两个新文件号。若菜单无法产生中性重显影，请记录限制，不能用原拍 JPEG 冒充同源重显影对照。原卡不要格式化。

## 2. USB 只读导入

关机后接数据线、开机，在机身选择 **Storage**。电脑出现的挂载目录应包含 `DCIM`；Linux 可用 `lsblk -o NAME,LABEL,RO,MOUNTPOINTS` 查看挂载点，再用 `findmnt -no OPTIONS --target /media/USER/CAMERA` 核对挂载选项。若要求介质严格零写入，先由系统以只读方式挂载并确认选项包含 `ro`。工具的 `camera_writes=false` 只表示程序没有向相机文件系统发出写入调用；读写挂载时系统可能更新访问时间。确认实际目录和文件名后，在仓库根目录运行：

```bash
python3 tools/usb_collect.py --source /media/USER/CAMERA --out sessions/first-usb \
  --file /DCIM/100OLYMP/P1010001.ORF \
  --file /DCIM/100OLYMP/P1010001.JPG
```

将示例挂载点和文件名替换为实际值；需要更多照片时重复 `--file`。输出目录必须是尚不存在、且**不在相机卡内**的路径。成功后检查 `sessions/first-usb/manifest.json` 中 `status=complete`、两张文件的 SHA-256、JPEG 的 `4608 × 3456` 尺寸和对应文件名。工具只验文件头与尺寸；后续用独立解码器检查完整 ORF/JPEG。

按系统流程卸载并断开 Storage，完成上述两张机内 RAW 重显影后重新连接。使用新会话再次导入**同一 ORF**及两张重显影 JPEG，例如：

```bash
python3 tools/usb_collect.py --source /media/USER/CAMERA --out sessions/after-edit \
  --file /DCIM/100OLYMP/P1010001.ORF \
  --file /DCIM/100OLYMP/P1010002.JPG \
  --file /DCIM/100OLYMP/P1010003.JPG
sha256sum sessions/first-usb/DCIM/100OLYMP/P1010001.ORF \
  sessions/after-edit/DCIM/100OLYMP/P1010001.ORF
```

两次 ORF 哈希必须一致；将中性、风格及原拍 JPEG 的尺寸和文件号分别记录。示例编号须替换为相机实测值。

## 3. 开始改机前的离线与实机门槛

先用样片锁定一款暖调负片目标，留出不参与调色的样片。随后验证原厂色彩字段对实际完整 JPEG 的作用范围；当前[路线 A 参数探针](CAVE_ENTRY.md)默认关闭，只有 CPU 模型证据。若参数达不到目标，再验证现有 LUT 路线的真实像素格式、写入所有权、缓存、完成通知和耗时。

刷写实验还需确认机身当前固件来源、可接受的更新入口、同版安装与失败恢复方法，并在能承担风险的试验条件下先验证原厂恢复。原厂色度路线已产出[柔彩升级候选](SOFT_CHROME.md)，尚待实机验证。`film.bin` 属于独立的软件 LUT 实验。首次实机验收以一次快门得到对应 ORF 与全尺寸风格 JPEG、关闭后回到原厂效果为准。
