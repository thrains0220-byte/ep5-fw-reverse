# D 诊断日志格式

诊断分支尝试在 ART 释放钩子通过原厂文件写服务生成 `EP5LUT/DIAG.LOG`。该钩子的写卡任务上下文、目录存在性和耗时均未在真机验证，不能称为安全点。每条记录固定 128 字节，小端，最多 8 条/次启动。诊断分支不改 ART packet、不申请 LUT 池、不写 JPEG 像素，但这些事实不能保证更新或运行安全。

2026-11-14 修订：旧 `build/ep5-diag-card-01` 包包含过宽的地址可读性判断，且每次刷新丢弃先前记录，**不得使用该旧包**。新源码记录缓冲地址但不解引用；每次以 `wb` 重写启动以来的有界内存快照，失败后留在内存中供后续重试。`wb` 可能截断旧文件，短写、断电和 close 失败仍可能留下不完整日志；这不是持久化保证。旧包未被重新生成，新模块仅供离线测试。

记录布局：

| 偏移 | 长度 | 字段 | 说明 |
|---:|---:|---|---|
| 0 | 4 | magic | `0x47414944` (`DIAG`) |
| 4 | 4 | sequence | 本次启动内递增序号 |
| 8 | 4 | jpeg_request | JPEG 请求结构地址 |
| 12 | 4 | buffer_addr | 请求 `+0` 的地址字段，缓冲含义未实机确认 |
| 16 | 2 | width | 请求 `+4` |
| 18 | 2 | height | 请求 `+6` |
| 20 | 2 | store_w | 请求 `+8` |
| 22 | 2 | store_h | 请求 `+10` |
| 24 | 4 | global_addr | `0x605f455c` 图像全局值 |
| 28 | 4 | context | 完成上下文地址 |
| 32 | 1 | fmt_byte36 | 请求 `[36]` 格式/标志字节 |
| 33 | 16 | sample | 保留，当前为零；不读取像素缓冲 |
| 49–51 | 3 | reserved | 0 |
| 52 | 4 | pool_ptr | 诊断时应为 0；若非 0 说明生命周期串入 |
| 56 | 4 | flags | 当前为零；未声明地址可读或已采样 |
| 60–127 | 68 | reserved | 0 |

## 解析边界

日志只记录 CPU 钩子看到的请求字段，不能证明缓冲可读、ISP 的 YUYV 字节序、DMA cache 一致性、JPEG 编码器读到的是同一块缓冲，或全幅处理耗时。诊断日志取回后，要和同一张照片的尺寸、EXIF、ORF 哈希一起记录。

## 生成与读取

离线模型：

```text
wsl --cd /mnt/d/0_Project/01Test/ep5-fw-reverse -e python3 tools/validate_diag_runtime.py --module build/diag-module-ui-review-01
```

读取真机日志：

```text
python tools/read_diag_log.py sessions/<pull>/DIAG.LOG
```
