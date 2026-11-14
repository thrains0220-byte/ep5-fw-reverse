# E-P5 1.8 Display/OSD API 静态 ABI 记录

本记录来自 `build/display-full.txt`，即官方 E-P5 1.8 解码 MAIN 的固定
反汇编。工具 `tools/inspect_display_api.py` 只解析地址、函数尾、寄存器保存
和直接 `call` 指令；不连接相机、不写固件、不生成刷机包。

运行：

```text
python tools/inspect_display_api.py --out build/display-api.json
python -m unittest tests.test_display_api
```

## 函数边界与调用约定

| API | 推定入口 | 锚点 | 栈帧/返回 | 直接调用 |
|---|---:|---:|---|---|
| `Disp_UpdateScreen` | `0x7e34deac` | `0x7e34deb5` | 保存 `d2,d3,a2,a3`，局部栈 `88` 字节；`ret [d2,d3,a2,a3],104` | 读取并记录 `img_handle[0..2]`、`osd_handle[0..2]`、`img_trans[0..2]`、`through_permit`、背景颜色字段；大量调用 `0x7e34dd16` 日志/字段报告 helper，最终调用 `0x7e354e62` |
| `Disp_LayerCustom` | `0x7e34e5ee` | `0x7e34e5f2` | `a0` 存于 `sp+32`；尾部 `ret [d2,d3,a2,a3],80`；前一条 `retf` 属于前面的代码 | `0x7e34dcf1`、`0x7e34e1a1`、多次 `0x7e34dd16` |
| `Disp_OsdUpdateColorPallet` | `0x7e34efa9` | `0x7e34efac` | `a0→a2`；读取 `a2+0/+4/+8`；尾部 `ret [d2,a2,a3],48` | `0x7e34dcf1`、多次 `0x7e34dd16`；条件路径调用 `0x7e388266`、`0x7e35477f`、`0x7e354852`、`0x7e354e62` |
| `Disp_ImgUpdateScreen` | `0x7e34f0d0` | `0x7e34f0d3` | `a0→a3`；尾部 `ret [d2,d3,a2,a3],76` | `0x7e34dcf1`、多次 `0x7e34dd16`；末尾条件路径调用 `0x7e354e62` |
| `Disp_ImgUpdateScreen_Async` | `0x7e34f220` | `0x7e34f223` | `a0→a3`；尾部 `ret [d2,d3,a2,a3],100` | `0x7e34dcf1`、多次 `0x7e34dd16`；条件路径调用 `0x7e35477f`、`0x7e354852` |

后四个起点未显示普通的寄存器保存序言；相邻 `ret` 的存在不证明它们是可直接
调用的函数入口，可能是共享帧或代码片段。须从真实调用点反向验证帧契约。

`0x7e34dd16` 和 `0x7e34dcf1` 在这些 API 中反复出现，当前只能标作
日志/字段检查 helper；不能把日志字符串的参数当成 API 参数。`0x7e354e62`、
`0x7e35477f`、`0x7e354852` 是带 `[d2,d3,a2,a3]` 的内部服务调用，具体显示
任务语义仍需独立恢复。

## 对 LUT UI 的实际意义

这些 API 显示 E-P5 有同步/异步图像层、多个 OSD 层和调色板对象；它们提供
了研究自定义菜单绘制的真实入口线索，但还不能安全直接调用。尚未恢复：

1. `a0` 指向的完整结构体大小、所有字段类型和所有权；
2. API 是否必须在 GUI 任务线程调用；
3. 图像/OSD 缓冲的生命周期、缓存同步和退出清理；
4. ART 状态回调到这些 API 的真实调用链；
5. 文本字库、OSD 图层坐标及语言资源绑定。

因此本记录不能作为把 LUT 菜单接入固件的充分条件。下一步应在 CPU 模型中
用固定只读结构验证字段访问和失败返回，再定位 ART 进入/重绘/退出回调的
真实调用者；UI 和 JPEG LUT 处理必须分别验收。
