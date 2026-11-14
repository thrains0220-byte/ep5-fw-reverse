# E-P5 ART/OSD 绘制链路：静态证据与下一步

本记录只描述 E-P5 1.8 解码 MAIN 的静态证据。工具不连接相机、不写入
固件或 SD 卡，也不生成可刷镜像。输入必须是项目锁定的 MAIN，SHA-256：
`dfe255e4d5a43329712c1fdfd6861ee1f3ef54a268b6096628bf045d8cc590df`。

## 可复现工具

```text
python tools/inspect_art_draw_chain.py --out build/art-draw-chain.json
```

工具以字符串指针引用作为反汇编导航锚点。每个地址是“包含该字符串
引用的指令地址”，不是已经证明的函数入口。输出明确标记
`camera_accessed=false` 和 `firmware_created=false`。

## 已确认的静态锚点

| 链路位置 | 指令地址 | 证据字符串/资源 | 目前能说明什么 |
|---|---:|---|---|
| GUI 消息循环 | `0x7eab7a7d` | `WinMain messageloop start` | GUI 任务消息循环存在；尚未证明 ART 启动调用链 |
| ART 任务标签 | `0x7e1c716c` | `ART_MAI` | 固件包含 ART 任务分类标签 |
| ART 拨轮事件 | `0x7eaf1fde` | `StArtMenu_EvtStChgJogDial` | 有原厂 ART 拨轮回调日志；事件矩阵入口见 `EP5_ART_UI_DISCOVERY.md` |
| ART 控制环事件 | `0x7eaf2fe5` | `StArtMenu_EvtStChgCtrlRing` | 有原厂 ART 控制环回调日志 |
| ART 退出 | `0x7eaf471b` | `StArtMenu_Exit` | 有原厂 ART 退出回调日志；退出清理不能跳过 |
| 屏幕层更新 | `0x7e34deb5` | `api_disp_Disp_UpdateScreen` | Display API 记录 `img_handle`、`osd_handle`、透明度和背景字段 |
| 自定义图层 | `0x7e34e5f2` | `api_disp_Disp_LayerCustom` | Display API 记录 3 个图像层和 3 个 OSD 层的尺寸、坐标、地址变换与层类型字段 |
| OSD 调色板 | `0x7e34efac` | `api_disp_Disp_OsdUpdateColorPallet` | 存在 OSD 调色板更新 API |
| 图像层同步更新 | `0x7e34f0d3` | `api_disp_Disp_ImgUpdateScreen` | 存在同步图像更新 API |
| 图像层异步更新 | `0x7e34f223` | `api_disp_Disp_ImgUpdateScreen_Async` | 存在异步图像更新 API |
| 显示同步 | `0x7eb1b470` | `OlyApiCameraCommon::getDispSync` | GUI 有显示同步状态读接口 |
| 显示同步取消 | `0x7eb1b489` | `OlyApiCameraCommon::cancelDispSync` | GUI 有取消显示同步接口；ART 退出/重绘必须考虑它 |
| OSD 资源名 | `0x7e23cf7c` | `Osd256` | 固件资源表包含 256 级 OSD 资源标记 |
| ART 缓冲资源名 | `0x7e23c9b9` | `BUFF_MEMORY_ART` | 固件资源表包含 ART 缓冲标记 |

## 与已有 ART 状态机的关系

### 进入回调的新增证据

`tools/inspect_art_callbacks.py` 对官方 MAIN 的 MN103 反汇编做了哈希保护，
把两个进入回调的直接调用边和间接 vtable 调用单独列出。第 5 列入口为
`0x7eaf19b7`，第 6 列入口为 `0x7eaf1a46`；两者都读取对象全局
`0x602c0d1c`，随后通过对象 vtable 的槽 0 和槽 8 调用。两条路径的事件
常量分别为 `0x91` 和 `0x9d`，并共享资源/状态服务调用。

这使“ART 进入回调 → 对象方法分派”的关系可复现，但仍不能把 vtable 槽
当作已知绘制函数。对象类型、槽位签名、绘制成员和 Display API 参数仍需
进一步恢复。工具输出明确保持 `camera_accessed=false`、
`firmware_created=false`。

`tools/inspect_art_state_machine.py` 读取以下静态结构：

- descriptor：`0x7edc0284`，11 个状态列、64 个事件行、183 个回调、64 个事件。
- 事件矩阵：`0x7edbff6c`；回调指针表：`0x7edbfc90`；事件表：`0x7edbfa90`。
- 进入回调表：`0x7edc022c`；退出回调表：`0x7edc0258`。
- `0x9031` 和 `0x9032` 的矩阵项分别能选到 `0x7eaf1fa3` 和 `0x7eaf2fb3`，但探针停在回调入口，不执行回调主体。

因此目前可以建立“事件矩阵 → ART 回调日志锚点 → Display API 资源锚点”
的静态研究路线，尚不能建立真实设备上“按键 → 状态对象 → 绘制 → 文本出现”
的完整执行证据。

## 不能从这些地址推出的结论

这些字符串引用不能证明：

1. 候选地址就是可直接调用的函数入口；
2. 某个 OSD API 的参数布局已经恢复；
3. ART 进入、绘制和退出回调一定经过上述每个 API；
4. 自定义字符串可以安全挂接到原厂字体/OSD 缓冲；
5. 在 ART UI 中加入动态 LUT 列表或强度控件不会破坏原厂状态机。

## 下一步（只读验证优先）

1. 以 `0x7eaf19b7`（ART 第 5 列进入回调）、`0x7eaf1a46`（第 6 列进入回调）和
   `0x7eaf46e8`（第 5 列退出回调）为边界，提取调用目标和常量引用，建立每个
   回调的局部调用图；当前已完成直接调用边和两个间接 vtable 边的静态清单，
   不把相邻函数当作同一回调。
2. 对 `api_disp_Disp_UpdateScreen`、`api_disp_Disp_LayerCustom`、
   `api_disp_Disp_OsdUpdateColorPallet` 做调用约定探针，先用固定参数在 CPU 模型
   中验证“只重绘一页”与“退出后清理”。探针必须在回调入口/返回处停止，不能接入
   相机固件。
3. 找到 ART 进入回调实际使用的菜单对象/vtable 和文本资源 ID 后，再验证固定容量
   UTF-16 名称快照；SD 文件任务只发布复制后的快照，不能把卡上指针交给 OSD。
4. 以上三项通过后，才设计动态 LUT 列表 UI；JPEG LUT 运行时仍须独立通过像素格式、
   缓存、全幅耗时和失败回退验收。UI 证据不能代替成像链路证据。

