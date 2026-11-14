# 两个开源项目能否搬到 E-P5：可行性核查

核查日期：2026-11-14
对象：
- fishcu/oly_fw_analysis（PEN-F 为主的研究 + HSL 色轮 mod + WiFi 配方客户端 + MN103 模拟器）
- cakelesscoder/caduceus-ep7（E-P7 1.1 固件补丁：29 种胶片模拟、HSLFX 编辑器、SD 卡 looks、颗粒、halation、bloom、log 视频、XPan 等）

本机证据：`data/ep5-stock/OLY_E_108_1800_0000_0000.BIN`（SHA cc59a4e1…，官方 1.8）。
探针脚本：`tools/research_ep5_portability.py`、`tools/research_ep5_deep.py`。
结果：`build/research/ep5_portability.json`、`build/research/ep5_deep.json`。
上游源码快照：`build/research/oly_fw_analysis-main`、`build/research/caduceus-ep7-main`。

---

## 0. 一句话结论

**不能把 Caduceus 的补丁直接刷到 E-P5。** 两者隔着两代 ISP（TruePic VI vs VIII，相差 7 年），
E-P5 没有 Caduceus 全部功能赖以存在的 COLOR Profile 系统，ART 管线也是另一套架构。
**但两个项目的方法论与我们已经在做的完全一致**，而且其中相当一部分能力 E-P5 原生就有，
可以用「不刷机」或「我们已验证的数据补丁」两条路拿到。下面逐项给依据。

---

## 1. 硬件 / 固件代差（硬证据）

| 项 | E-P5（本机） | E-P7（Caduceus） | PEN-F（fishcu） |
|---|---|---|---|
| 处理器 ISP | TruePic VI（2013） | TruePic VIII（2020） | TruePic VIII |
| CPU | MN103/AM33 | MN103/AM33 | MN103/AM33 |
| main 组件大小 | 15,728,576 B | 26,214,336 B | 26 MB 级 |
| main CPU 基址 | 0x7E101020 | 0x60020020 | 0x60020020 级 |
| 容器格式 | OE 块（同族） | OE 块 | OE 块 |
| ART 执行架构 | `art_img_cm_exec` / `art_cpu_exec`（效果函数指针） | job / work-list / combiner（stage 0x0901/0x0902） | 同 E-P7 |
| `combiner`/`worklist` 字符串 | **0** | 有 | 有 |
| COLOR Profile 系统 | **无**（`PROFILE` 字符串 1 处，`COLORTONE` 56 处） | 有（`PROFILE` 21、`COLORTONE` 213） | 有 |
| 照片色彩调节 | iFinish gamma + 饱和标量；ART 用 16 节点色度曲线 | 每 profile 12 扇区 H/S/L + tone | 同 E-P7 |

要点：
- Caduceus 的**每一个** look / 编辑器 / film-page / bundle 功能都挂在 COLOR Profile 槽上。
  E-P5 没有这个宿主（它自己的移植文档 PORT_EM10IV.md 也确认：无 profile 的机型需要「重新设计宿主，不是搬地址」）。
- Caduceus 对同代机型的静态签名匹配率：E-M10 IV 47%、E-M5 III 36%、OM-3 26%。
  E-P5 是**上一代** ISP，连这套 job/combiner 架构都不存在，匹配率会远低于这些数字，且 GUI/菜单/字符串 id 全部要重推。
- 因此「下载 Caduceus 的 edits.json 改个基址刷进去」这条路**不存在**。

---

## 2. E-P5 原生已有、可被利用的能力（本机已核实）

这些是 E-P5 固件里**真实存在**的字符串 / 表 / 接口，是我们做功能的落点：

| 能力 | 本机证据 | 对应上游概念 |
|---|---|---|
| 13 个 ART 模式 × 2 轴 16 节点色度曲线 | 26 张恒等曲线表，0x7e438a28 起；CMIO 分派 0x7e22a023 | Caduceus film look 的色彩部分（我们已用 HQ 曲线实现 7 槽） |
| 10 个 ART 滤镜（菜单） | OSD 0x2ce18e…：负片冲印/立体/戏剧/柔和怀旧/照片怀旧颗粒/柔光/淡化增亮/浓郁色调/柔焦/针孔 | Caduceus Art Effects |
| Color Creator（色彩波轮） | main 0x7ec42803 `COLOR_CREATOR_MODE_SETTING_JUDGE_OK`；OSD 0x364cb4 `Color Creator` | PEN-F COLOR 波轮的「近亲」，但是独立拍摄模式 |
| My Set 1–4（我的设定） | OSD 0x2cefb0…0x2cefda | Caduceus COLOR1–4 槽的 E-P5 等价宿主 |
| 普通照片模式 iFinish gamma + 饱和 | `piFinishPrm->rgbgamma/ygamma/nv/spc`，`pImgParam->chSaturation` | Caduceus tone + 饱和 |
| WB 偏移 RB/GM | EXIF `WBAdjustRB`/`WBAdjustGM` | Caduceus WB shift |
| 颗粒硬件 | `art_filter_06_rough_monochrome`、`art_random_generator32`、颗粒 mask 曲线 | Caduceus grain（但 E-P5 只 gate 给粗糙单色） |
| 录像 ART | `MOV_ART`、`MODE_COLORTONE` | Caduceus movie colour |
| **WiFi CGI 遥控** | `set_camprop.cgi` 支持 `artfilter`/`takemode`/`wbvalue`/`isospeedvalue`…；`exec_shutter.cgi`（1st/2ndpush）；`exec_shuttermisc.cgi`（startliveview） | fishcu penf_wifi 配方客户端 |
| **SD 参数覆盖 + 调试壳** | `PARAMDT/CP??????CSV` 加载器（0x7e27c3fd）；`U_SHELL`；`WIFI SHELL`/`S_SHELL`（0x7e9e04ff，端口 23） | fishcu WIFI_DEBUG（F971 门） |
| SD 文件 API | `FILECLBK`、`fileif_fopen/fread/fseek/filesize_get` | Caduceus sd_bundles 加载器 |
| FF 代码空洞 | ≥512B 空洞 19 处，最大 0x7ef4b63f 约 743KB（需证 section 驻留） | Caduceus code-space |

---

## 3. 逐项可行性（用户关心的功能）

分四档：✅ 已验证 / 🟢 高可行 / 🟡 中等（需攻关） / 🔴 很难或不可行。

### ✅ 已验证（我们自己的成果，就是 E-P5 版的 Caduceus 色彩）
- **7 槽 HQ 胶片色度曲线**（Velvia/Portra400/Gold200/ClassicChrome/Ektar/CineStill/森山黑白），
  纯数据补丁，RC2 机制，真机成片 + 官方恢复已验证。安全版 `build/film-safe-7`。
- 这正是 Caduceus「film simulation 色彩部分」在 E-P5 上的等价实现，只是宿主是 ART 槽而非 COLOR profile。

### 🟢 高可行 —— 不刷机就能拿到的「换风格」体验
1. **WiFi 遥控切换 ART / 照片模式 / WB / ISO + 遥控快门。**
   E-P5 原生 `set_camprop.cgi?com=set&propname=artfilter&value=…` 与 `exec_shutter.cgi`。
   做一个桌面/手机小工具（fishcu penf_wifi 的思路，换成 E-P5 的 CGI 协议），
   连上相机私有 WiFi 就能「点一下换胶片风格、再点一下拍照」。**零固件风险。**
   待办：真机抓 `get_camprop.cgi?com=desc&propname=desclist` 与 artfilter 取值表，确认 value 编码。
2. **SD 参数覆盖（PARAMDT/CPxxxxxx.CSV）+ WiFi 调试壳。**
   fishcu 在 PEN-F/E-M5 III 上证实的「不刷机改参数 + 端口 23 壳」机制，E-P5 有同族加载器与 U_SHELL/WIFI SHELL。
   若 E-P5 的使能门（PEN-F 是 F971）能被 CSV 触发，就能**不刷机**实时调 ISP 参数、读内存、验证曲线。
   待办：定位 E-P5 的使能参数 id 与 CSV 触发路径（0x7e27c3fd 上游），真机验证。这是「免砖调试」的关键钥匙。

### 🟡 中等 —— 需要一次数据/代码补丁 + 真机取证
3. **SD 卡热换 LUT / looks（松下 S9 体验）。**
   我们的 mode-3 运行时（`firmware/ep5_art_entry.c`）+ Caduceus sd_bundles_v3 的「不写 loaded image、malloc 池发布句柄」安全模式。
   E-P5 有 fileif API。卡上放 `EP5MOD/LOOKS.BIN`，半按快门加载，换风格不用重刷。
   待办：fileif 钩子点 + 静态像素契约真机取证（当前唯一硬阻塞之一）。
4. **更多胶片槽 + My Set 当「配方库」。**
   13 个 ART 色度组都可改；My Set 1–4 可存「ART+曲线+WB+对比」整套。
   把 7 槽扩到更多风格，并用 My Set 做一键召回。纯数据，风险同 RC2。
5. **普通照片模式（P/A/S/M）的胶片 tone。**
   改 iFinish 的 rgbgamma/ygamma + 饱和标量，让 Natural/Vivid 等也带胶片曲线，**不必进 ART**。
   待办：定位每个 colortone 的 gamma 表指针与饱和映射（0x7e3afe90 附近），证明只改目标模式。

### 🔴 很难 / 暂不可行（E-P5 架构限制）
6. **完整 HSLFX 色轮编辑器（每色 H/S/L + 机内编辑页）。**
   E-P5 没有 COLOR profile UI 宿主；Color Creator 是独立模式、不是逐 profile 的 12 扇区 H/S/L。
   要做需新建编辑器 UI + 设置存储 + 校验器，等于重写 Caduceus 的 GUI 层，工作量极大、砖风险高。
   **替代**：用 Color Creator 原生波轮 + 我们的曲线，或 WiFi 工具调 HSL 近似。
7. **Halation / bloom / clarity（空间效果）。**
   需要 E-P5 的 blur/blend 路径参数（Caduceus 在 E-P7 上也还没完全定位）。E-P5 效果架构不同，需从头逆向。
8. **真 log 视频 / XPan 21:9 / 9 小时录像。**
   E-P5 录像管线与传感器读出与 E-P7 不同，Caduceus 这些补丁的钩子不存在。需独立逆向，收益低、风险高。
9. **彩色照片颗粒。**
   E-P5 颗粒硬件只 gate 给粗糙单色（同 PEN-F 的三道门）。可借鉴 Caduceus grain_cpu 的 CPU 颗粒，
   但要在 E-P5 效果架构里找落点，属🟡偏🔴。

---

## 4. 关于「色彩波轮」

用户想要的「色彩波轮」= PEN-F/Caduceus 的 COLOR 波轮（12 扇区饱和 + H/L）。
- E-P5 **没有**这个波轮。它有 **Color Creator**（色相/饱和环），但是一个独立拍摄模式，不是逐 profile 的 HSL 编辑。
- fishcu 的 PEN-F HSL mod 是「给已有的 COLOR 波轮加 H/L 页」——E-P5 没有可加的波轮，所以**不能照搬**。
- 现实路径：
  a) 用 E-P5 原生 Color Creator 当「波轮」体验（不刷机）；
  b) 我们的 ART 色度曲线提供胶片色彩（已验证）；
  c) 若要机内逐色 HSL，需新建编辑器（🔴，不建议现在做）。

---

## 5. 建议的推进顺序（以上相机能用为前提）

1. **先刷安全版 safe-7 并真机验收**（ART 正常出图、7 槽色彩、录像、可恢复）。这是当前唯一硬阻塞。
2. **WiFi 遥控换风格工具**（🟢，不刷机）：抓 CGI 取值表 → 桌面工具一键切 ART/拍照。立刻可用。
3. **PARAMDT CSV + WiFi 壳免砖调试**（🟢，不刷机）：定位使能门 → 真机验证 → 成为后续所有攻关的取证通道。
4. **SD 热换 LUT**（🟡）：fileif 钩子 + 像素契约真机取证 → 卡上换风格。
5. **扩槽 + My Set 配方库 + 普通模式 tone**（🟡，纯数据）：丰富 P/A/S/M 直出。
6. 颗粒/halation/完整 HSL 编辑器（🔴）：放在后面，按需立项。

每一步都遵守防砖硬约束：探针证明只改目标模式、共享/录像回原厂、效果指针状态正确；
新曲线未真机实拍前只标 hardware-functional-candidate；**清零效果指针=已证实黑屏，禁止再上机**。

---

## 6. 与上游的关系（避免重复造轮子）

- 容器解码：我们已用 fishcu 的 `oly_container.py`（`external/oly_fw_analysis`）。
- MN103 工具链：本机 `toolchains/mn103`（gcc 14.3 + objdump）已可反汇编 E-P5 main。
- 模拟器：fishcu 的 `penf_emulator` / `mn103_runner` 是 PEN-F 专用，E-P5 需自己的内存模型；
  我们已有 `build/chroma-dump/ep5-contract-probe`（自包含探针）。
- Caduceus 的**安全设计**值得直接借鉴：sd_bundles_v3「不写 loaded image」、plugin「boot 不读卡」、
  每步真机验收顺序（官方包→恢复→无害文本→数据→空钩子→逐功能）。我们的 safe-7 已遵循同一原则。
- **不抄地址、不抄 edits.json**：两代 ISP 地址/架构不通用，只抄方法与格式思想。
