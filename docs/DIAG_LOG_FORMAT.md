# D 诊断日志格式

`EP5LUT/DIAG.LOG` 由诊断分支在 ART 释放安全点通过原厂文件写服务生成。每条记录固定 128 字节，小端，最多 8 条/次启动。诊断分支不改 ART packet，不申请 LUT 池，不写 JPEG 像素；原厂成像路径照常运行。

记录布局：

| 偏移 | 长度 | 字段 | 说明 |
|---:|---:|---|---|
| 0 | 4 | magic | `0x47414944` (`DIAG`) |
| 4 | 4 | sequence | 本次启动内递增序号 |
| 8 | 4 | jpeg_request | JPEG 请求结构地址 |
| 12 | 4 | buffer_addr | 请求 `+0`，实际 YC 缓冲地址 |
| 16 | 2 | width | 请求 `+4` |
| 18 | 2 | height | 请求 `+6` |
| 20 | 2 | store_w | 请求 `+8` |
| 22 | 2 | store_h | 请求 `+10` |
| 24 | 4 | global_addr | `0x605f455c` 图像全局值 |
| 28 | 4 | context | 完成上下文地址 |
| 32 | 1 | fmt_byte36 | 请求 `[36]` 格式/标志字节 |
| 33 | 16 | sample | 缓冲开头 16 字节（只读样本） |
| 49–51 | 3 | reserved | 0 |
| 52 | 4 | pool_ptr | 诊断时应为 0；若非 0 说明生命周期串入 |
| 56 | 4 | flags | bit0=地址可读，bit1=样本已读 |
| 60–127 | 68 | reserved | 0 |

## 解析边界

日志证明的是 CPU 钩子看到的请求字段和缓冲可读性。它不能单独证明 ISP 的 YUYV 字节序、DMA cache 一致性、JPEG 编码器读到的是同一块缓冲，或全幅处理耗时。诊断日志取回后，要和同一张照片的尺寸、EXIF、ORF 哈希一起记录。

## 生成与读取

离线模型：

```text
wsl --cd /mnt/d/0_Project/01Test/ep5-fw-reverse -e python3 tools/validate_diag_runtime.py
```

读取真机日志：

```text
python tools/read_diag_log.py sessions/<pull>/DIAG.LOG
```
