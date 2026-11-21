# E‑P5 胶片色轮的操作与验证

2026-11-21。色轮编辑器已经能用现有菜单按键完成选色、调节、取消和保存。保存后的三个轴会实际改变 17³ RGB16 色表。已在宿主测试程序渲染中文界面，并用 MN103 编译器构建目标文件。E‑P5 液晶屏上的实际显示和拍摄耗时待真机验证。

## 操作

在风格列表中，用上下键选中风格，按 OK 确认，再按一次 OK 开色轮。如果调整了基础风格的强度，第一次 OK 会确认新强度。进入色轮后，上下键移动焦点，左右键调节当前项目。

29 款风格共分三组，各有 14、14、1 款。打开 `ep5_camera_menu_init()` 对应的菜单后，先用上下键选组、OK 进列表。MENU 从色轮退回风格列表，再按回到分组，再按回到拍摄。风格列表右上角显示当前组，画面左边的星号标记已经确认的风格。[分组画面](../build/caduceus29/Menu-groups.png) · [风格列表画面](../build/caduceus29/Menu-looks.png)

| 项目 | 操作结果 |
| --- | --- |
| 色区 | 循环选择十二种颜色。色环标出当前色区，中央和右侧显示中文名。 |
| 色相、饱和度、明度 | 色相与明度各有 −15 至 +15，饱和度 −5 至 +5。编辑一个色区会平滑影响邻近色相。 |
| 重置本色、重置全部 | 按 OK 将当前色区或整轮草稿恢复为零。 |
| 保存调整 | 按 OK 提交给调用者并返回列表。菜单键取消草稿。 |

绘图器使用可量度的 42 列 × 13 行原厂菜单字体单元。机身绘图后端负责提供原厂字体、字符尺寸和当前调色板。主机预览采用本机中文字体，展示按键实际产生的命令。预览中的 Gold 处于红色区，色相为 +2，饱和度为 −2。[主机预览](../build/wheel-rgb17/Wheel-Editor.png)

## 接入

`firmware/lut_wheel_view.h` 提供 `ep5_wheel_controls_event()`。在串行的菜单任务中把原有按键交给它，保留已有列表返回值 0–3。一次性清零 `ep5_wheel_editor` 和 `ep5_wheel_edit`，之后可以使用 `ep5_wheel_decode()` 恢复已保存的调整。返回 `EP5_WHEEL_OPEN` 时进入色轮，其他编辑事件刷新画面。`ep5_wheel_draw()` 只调用传入的有界填色和 UTF-16 文字接口，每帧 16 次填色、16 次文字。绘图目标小于 42×13 或选择已过期时返回 0，调用者应重画风格列表或状态页。

每次按键和绘图都会检查当前卡的挂载标识、菜单 generation 和被选择风格的编号、校验值、picture mode、variant。换卡、重新载入列表、闭菜单或变更风格时，旧草稿不能提交。给每次挂载分配不同的非零标识，卡移除时立即使标识失效。若调用者另行保留多个风格的编辑，按 `ep5_wheel_same_look()` 查找对应条目。

统一菜单的宿主使用 `ep5_camera_menu_event()`、`ep5_camera_menu_step()`、`ep5_camera_menu_draw()`。按键和绘图不会读文件，文件任务在 `step()` 中调用既有 `lut_bank` 加载器。拍摄通过 `ep5_camera_menu_capture()` 取得卡号、组号、选择版本、风格、强度和该组已确认的色轮。后台合成完成时用 `ep5_camera_menu_choice_current()` 丢弃过期结果。换组或重新确认会生成新的选择版本，在当前挂载内分别保留每组各槽位的编辑。宿主四项测试遍历实际卡包的全部 29 款，对照名称、编号、位置和色表校验值，并覆盖跨组完全相同的索引、半读换组和退卡。可用 `python3 tests/test_lut_camera_menu.py -v` 复验。

`EP5_WHEEL_SAVED` 交付有符号的 H/S/L 调整数值。后台任务从选中风格的原始 RGB16 表开始，调用 `ep5_wheel_bake()` 分段生成新表。每次传入网格起点和节点数，例如每批 37 个节点。各段完成后才将目标表交给现有采样器。校验 `saved` 与当前活动风格仍匹配，在发布前再次检查卡片和选择的有效期。处理时长、资源分配和跨任务同步由接入方负责。调整量相对于原始表，重编辑时要使用保存的原表，避免重复叠加。

基础表与目标表可分开，亦可由调用者独占同一块后台缓存原位处理。部分重叠、非法调整、越界或空间不足时返回 0。拍摄中的缓冲需要等现有读取者释放后才能复用。没有基础表时可传入 NULL、0，从恒等映射构建色轮。色轮默认输入为已经转为显示 RGB 的可采样数据。颗粒、光晕和配方的整体色调曲线由成像流程的其他步骤承担。

## 保存格式

`ep5_wheel_encode()` 与 `ep5_wheel_decode()` 处理 56 字节的 `EP5W` v1 记录。编码采用小端。第 0–3 字节为魔数，第 4–5 字节为版本 1、色区数 12。第 6–9 字节为 uint16 picture mode、uint8 variant、uint8 风格编号，第 10–11 字节保留为零，第 12–15 字节为底层原始风格的 CRC32。第 16–51 字节分别存放 H、S、L 的 12 个有符号字节。第 52–55 字节为前 52 字节的标准 CRC32。解码依次验证完整长度、版本、CRC、身份和值域。

### 保存到卡与重新装入

每组沿用本组索引的目录，为十四个槽分别保留 `W01.EP5` 至 `W14.EP5`。例如第一组和第二组的第一个槽分别为 `EP5LUT/W01.EP5` 和 `EP5LUT/B02/W01.EP5`。载入后再核对记录内的模式、变体、色表编号和原表 CRC。同名配方分属各自的组。重新打开一个组时，菜单会读取该组已有的调整并在完整载入后开放选择。缺少记录使用基础配方。损坏、过长或读失败的记录会在相应行显示提示。若卡上合法记录属于已经替换的旧表，当前风格使用基础配方。

初始化菜单后，用 `ep5_camera_menu_attach_store()` 注册当前卡的读取和原子替换接口。菜单任务收到 `EP5_CAMERA_SAVE_REQUEST` 后即可继续响应按键和绘图。文件任务成功提交后，拍摄才使用新调整。排队期间可按 MENU 撤销，正式提交期间会显示正在保存。写失败时，菜单保留草稿供重试，拍摄沿用上次成功的设置。

用独立文件任务时，菜单所有者调用 `ep5_camera_wheel_take()` 将请求复制给它。文件任务单独调用 `ep5_camera_wheel_execute()`，随后把结果交回菜单所有者调用 `ep5_camera_wheel_finish()`。只有 `execute` 可以访问卡。提交成功返回 `EP5_CAMERA_SAVE_COMPLETE`。退出页面、重新读组或换卡后，迟到的读取结果会被丢弃。在没有并发的宿主驱动中，也可以由同一文件任务调用 `ep5_camera_menu_step()` 完成这三个步骤。

卡服务需为每次插卡分配新的非零挂载标识，在拔卡时撤销旧标识并通知菜单。文件任务应把一次操作绑定到其原始介质，在原子替换处核对介质身份。成功时发布完整记录，报告失败时保留上次已提交的版本。已发布作业的后端上下文需要保留到回调结束。测试用同目录临时文件和原子重命名在宿主文件系统验证这些行为。E-P5 实际文件服务对替换、刷新以及意外断电的保证仍待实机核实。

用 `wsl -e python3 tests/test_lut_camera_menu.py -v` 可复跑八项菜单测试。四项保存测试使用实际目录，每次重启测试启动新进程，比较不同卡和不同组的同名风格，检查写失败后旧文件的字节、再次保存、提交前撤卡，以及重复或迟到的工作结果。三个拍摄回归可用 `python -m unittest discover -s tests -p test_sd_photo.py -v` 复跑，其中一项检查色轮记录只改变与自身匹配的色表。

## 复验

在仓库根目录的 POSIX shell 运行。两项 C 测试均启用了未定义行为检查，`--trace` 输出实际绘图命令。最后一条命令使用系统中已有的中文字体。

```sh
wheel_src="firmware/lut_wheel_view.c firmware/lut_wheel.c firmware/lut_menu_adapter.c firmware/lut_menu.c"
cc -std=c99 -O2 -Wall -Wextra -Werror -fsanitize=undefined -fsanitize-undefined-trap-on-error -Ifirmware tests/test_lut_wheel.c $wheel_src firmware/lut.c -o /tmp/ep5-wheel-test
/tmp/ep5-wheel-test
python3 tests/test_lut_wheel_parity.py /tmp/ep5-wheel-test
cc -std=c99 -O2 -Wall -Wextra -Werror -fsanitize=undefined -fsanitize-undefined-trap-on-error -Ifirmware tests/test_lut_wheel_draw.c firmware/lut_wheel_draw.c $wheel_src -o /tmp/ep5-wheel-draw
mkdir -p build/wheel-rgb17
/tmp/ep5-wheel-draw --trace > build/wheel-rgb17/Wheel-Editor.trace
python3 tests/test_lut_wheel_preview.py build/wheel-rgb17/Wheel-Editor.trace /path/to/CJK-font.ttc build/wheel-rgb17/Wheel-Editor.png
```

23 组配方逐一核对全部 4,913 个 RGB 节点。C 整数实现和 Studio 浮点参考间的最大通道差为 57/65,535，约 0.22 个八位色阶。全零配方逐字节一致。宿主测试也覆盖分段、原位合成、选区以外的灰阶和绿色、取消及过期选择。目标编译使用 freestanding C99，三个模块没有可写全局数组。整数除法需工具链的 `__divdi3` 支持。
