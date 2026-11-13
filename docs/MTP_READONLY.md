# Windows 上通过 MTP 读取 E-P5 原片

在相机的 USB 菜单选择 **MTP**；Windows 应能将其识别为便携设备。只连接一台便携设备，退出正在占用相机的导入程序。在仓库根目录用 Windows Python 3.11 运行以下命令。首次使用可在本地虚拟环境安装 `python -m pip install comtypes==1.4.15`，也支持项目已有的 `build/usb-python-deps/`。程序不会安装驱动。

```console
python tools/mtp_collect.py inspect --session ep5-before-list --limit 120
```

打开电脑上的 `sessions/ep5-before-list/manifest.json`。程序先核对 PnP 中的 USB VID/PID 为 `07B4:012F`，再核对设备模型为 `E-P5`；多设备或型号不符均停止。清单包括 Windows 报告的版本、电量和有限的目录元数据。**WPD 的版本字符串不能确认机身固件版本**：本次 E-P5 的机身菜单显示 1.8，MTP 报告 1.00。拍摄前后仍应记录机身菜单。

`inspect` 默认最多记录 120 个对象；`--limit` 可设为 1–512，最多枚举五层。若 `inventory_limited` 为真，清单只是已读取部分，不表示卡上没有其他照片。用 `objects` 里的 `id` 和 `filename` 挑出要取的原片，每张分别指定。以下编号仅作示例：

```console
python tools/mtp_collect.py pull --session ep5-before-originals --id o76:PA310067.ORF --id o77:PA310067.JPG
python tools/check_trial_photos.py --before sessions/ep5-before-originals/PA310067.JPG
```

第二条的解码依赖见[样片检查说明](TRIAL_PHOTOS.md)。每次采集给一个新的会话名称，只能由字母、数字、横线和下划线组成，且以字母或数字开头。不接收输出路径，也不会覆盖已有会话。原片和清单只保存在本仓库被 Git 忽略的 `sessions/` 下；请从公开报告中去掉照片、EXIF 身份信息、目录和对象名。程序不查询序列号，不保存完整 PnP 路径。

`pull` 在打开数据流前核对所选对象当前的原始文件名、内容类型和大小；对象 ID **不是跨连接的永久标识**，[Windows WPD 对象文档](https://learn.microsoft.com/en-us/windows/win32/api/portabledeviceapi/nf-portabledeviceapi-iportabledevicecontent-getobjectidsfrompersistentuniqueids)对此有说明。请在同一机身、同一卡上紧接着清单操作；换卡、重连或新增/删除照片后重新列目录。文件号也会循环，单靠文件名不能证明为原先那次拍摄。

单次最多 16 个指定对象，每个不超过 64 MiB。连接只请求 `GENERIC_READ`；[默认资源流](https://learn.microsoft.com/en-us/windows/win32/api/portabledeviceapi/nf-portabledeviceapi-iportabledeviceresources-getstream)只请求 `STGM_READ`。工具逐块计算 SHA-256，比较实际长度及读取前后的对象元数据，检查 JPG/ORF 文件头，通过后才以原文件名保存。出错时会话标为 `incomplete`；已完整复制的文件有单独记录，未完成的文件不会发布。只有 `complete` 表示请求的对象都成功复制。它不能证明相机装过候选固件、胶片生效或恢复成功。

这两个命令都不写卡、不操作快门、不进入更新模式，也不执行厂商命令。要在相机上拍照请先断开 USB，拍完重新进入 MTP 并建立新会话。
