# EP5 LUT Studio v2 — 使用指南

## 启动

```bash
python tools/run_lut_studio_v2.py
```

或打包为 EXE（需 PyInstaller）：
```bash
build\lut-studio-packenv\Scripts\pyinstaller.exe --distpath build/lut-studio-dist-v2 --workpath build/lut-studio-pyinstaller-v2 --specpath build/lut-studio-spec-v2 --name EP5LUTStudioV2 --windowed --noconfirm tools/run_lut_studio_v2.py
```

## 界面布局

- **左侧**：胶片库，按分类标签（彩色负片/反转片/黑白/电影/自定义）
- **中央**：原图/效果分屏预览，拖动分割线对比
- **右侧**：7 个机内 ART 槽位卡片 + 固件生成按钮

## 工作流程

### 1. 导入风格

- 点击"导入 .cube"或 Ctrl+O，选择任意 .cube 文件
- 内置 19 种胶片风格已自动载入（Portra/Gold/Velvia/Ektar/CineStill/森山等）
- 拖放 .cube 文件到窗口也可导入

### 2. 预览

- 在左侧选择一个风格，中央即时显示效果
- 拖动分割线对比原图/效果
- 强度滑块调节 0–100%
- 可加载自己的照片（JPEG/PNG，需 sRGB 标记）

### 3. 绑定到 ART 槽位

7 个槽位对应机内 ART 菜单：

| 槽位 | 机内菜单名 | 操作 |
|---|---|---|
| 人像柔暖 | 柔焦效果 | 直接选 |
| 胶片色彩 I | 针孔相机 I | 右键切 I |
| 胶片色彩 II | 针孔相机 II | 右键切 II |
| 胶片色彩 III | 针孔相机 III | 右键切 III |
| 风景鲜艳 | 立体效果 | 直接选 |
| 电影色调 | 浓郁色调效果 | 直接选 |
| 森山黑白 | 负片冲印效果 | 直接选 |

选择风格后点击槽位的"绑定当前风格"按钮。

### 4. 生成固件

点击"🔧 生成 7 槽固件…"，选择输出目录。

生成物：
- `firmware/DCOLYMP/E1089999.BIN` — 可刷固件
- `kit/E-P5-1.8-Film-CUSTOM-7.zip` — 含固件 + 说明
- `kit/E-P5-1.8-STOCK-RECOVERY.zip` — 官方恢复包

### 5. 刷入相机

1. 备份 SD 卡照片
2. 将 `DCOLYMP/E1089999.BIN` 放到 SD 卡根目录的 `DCOLYMP` 文件夹
3. 关机 → 按住 OK 开机 → AF 灯常亮→快闪→熄灭
4. 关机 → 正常开机
5. ART 菜单查看新名称，拍 RAW+JPEG 对照

恢复原厂：用恢复包同法刷入。

## 能力边界

色度曲线（9 节点非线性）能表达：
- 饱和度缩放（浓艳/低饱和/漂白）
- 微偏色（暖/冷）
- 完全去色黑白
- 按亮度区间分段控制（阴影去饱和/中间调增强/高光保护）

不能表达：
- 色相旋转（红→橙）
- 亮度 S 曲线（高反差）
- 颗粒、暗角

黑白风格为纯去色；高反差请用机身对比度设置补足。

## .cube 导入说明

任意 .cube 文件会被投影到 Cb/Cr 两轴 9 节点曲线。投影会丢失色相旋转和亮度曲线部分，
但保留饱和/偏色取向。导入时显示误差报告（mean RGB error）。

误差 < 5：优秀（几乎完整保留）
误差 5–10：良好（取向正确，细节有损）
误差 10–20：近似（方向对，损失明显）
误差 > 20：较差（建议用机身设置补足）

## 技术机制

- 纯数据补丁（ROM 色度表 + 效果指针清零 + 菜单改名）
- 无新增可执行代码，与已真机验证的 RC2 同风险等级
- 录像/共享模式全部重路由到原厂恒等表（模式 72 锚点）
- RAW (ORF) 完全不受影响
- 全幅 4608×3456，一次 JPEG 压缩

## 校验

构建后自动通过：
- 写入器隔离探针（7 照片模式变化，7 共享模式回原厂，其余 240+ 不变）
- 完整拍摄路径探针（7槽×3录像状态=21组）
- 菜单标签验证

## 文件索引

- `ep5studio/app_v2.py` — UI 主程序
- `ep5studio/firmware.py` — 固件构建接口
- `tools/build_custom_full.py` — 自定义 7 槽构建器
- `tools/build_full_film.py` — 默认 7 槽构建器
- `tools/cube_to_hq.py` — .cube → 9 节点曲线拟合
- `tools/film_pack/verify_full_custom.py` — 自定义固件校验
- `tools/run_lut_studio_v2.py` — 启动入口
