# 没有读卡器时：原生 Wi-Fi 读取入口

E-P5 1.8 原版固件包含 OI.Share 2.20 能力描述、`get_caminfo.cgi`、`get_commandlist.cgi`、`get_imglist.cgi` 及 ORF 的 HTTP 文件类型处理。内置网页给文件生成直接下载链接。默认地址字符串为 `192.168.0.10`。

这是原版固件的静态证据，尚未连接当前机身验证。能够下载原图不代表取得了可编辑的机内图像缓冲区。已识别的文件接口主要用于读取；尚未建立通过原生 Wi-Fi 把诊断文件写入 SD 的方法。

## 最小读取

1. 在相机上开启正常的 Wi-Fi 连接功能，使用自己的连接信息让电脑加入相机网络。仅有一个无线网卡时，电脑的普通网络连接可能暂时断开；本项目不会自动切换网络。
2. 若代理/VPN 拦截局域网，先确认到相机的路由；以下命令只让 curl 不使用 HTTP 代理，不会修改系统网络设置。
3. 在终端读取机型信息：

```bash
curl --fail --max-time 8 --noproxy '*' --user-agent OlympusCameraKit \
  http://192.168.0.10/get_caminfo.cgi
```

确认返回的是自己的 E-P5，再读取能力和连接模式：

```bash
curl --fail --max-time 8 --noproxy '*' --user-agent OlympusCameraKit \
  http://192.168.0.10/get_commandlist.cgi
curl --fail --max-time 8 --noproxy '*' --user-agent OlympusCameraKit \
  http://192.168.0.10/get_connectmode.cgi
```

这些命令没有设置参数、切换拍摄模式或释放快门。若请求失败，保留错误信息，不要自动重复发送其它控制命令。机身信息可能含序列号；反馈机型和版本即可。

## 原图线索

```bash
curl --fail --max-time 8 --noproxy '*' --user-agent OlympusCameraKit \
  'http://192.168.0.10/get_imglist.cgi?DIR=/DCIM'
```

列表返回后，以其真实目录名继续列出对应目录。固件的网页直接链接到文件路径；后续可依据返回的实际文件名下载原图。请不要使用 `get_resizeimg.cgi` 取得所谓“全尺寸”参考：固件列出的该接口最大尺寸为 2048，它是缩图路径。

需要的校色素材是 E-P5 自己的 ORF 与同次拍摄的全尺寸 JPEG。普通 Wi-Fi 读取成功后再验证原图下载、长度和图像尺寸，不把缩略图当作原始画质依据。

## 目前的硬件边界

USB、读卡器、Wi-Fi 三者中，只要有合适的访问方式，便能继续取得部分实机资料。胶片核心接入与稳定性验收最终仍需相机实际执行。若这三条路径目前都不可用，离线测试无法证明机内成片。
