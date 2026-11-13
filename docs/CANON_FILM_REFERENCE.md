# 老佳能的机内胶片模拟：E-P5 借哪一部分

2026-11-13 核查作者网站、仓库文件索引和指定提交的纯文本源码。Soup Engine 默认分支读到 [38f4d88（11 月 11 日）](https://github.com/jiijii0/soup-engine/commit/38f4d88165199e8b78577bc0c1b774ff541b01a4)，M-Film 读到 [e76587c（11 月 12 日）](https://github.com/HNGSeries/mfilm-canon-film-simulation/commit/e76587c6eed9d894f7cc6be5021924b73e908ab7)。这是近期仍有活动的实例，不是使用人数排名。没有下载或运行第三方相机程序、复制商业胶卷或改写相机。

**最适合借用的是卡上换风格、每张照片固定所选风格、后台分步显影这三件事。** 是否保留原始 RAW、输出多少像素、有没有二次 JPEG 压缩，要逐条核对。Canon 上能做成的产品体验，不能证明 Olympus 已提供相同的显影阶段、调用接口或安全退出方式。

## The Ritual：参考交互，不假定实现

[作者的机内操作说明 1.2.1](https://latentstudios.art/firmware/guide/)按 5D、5D II、5D III、6D 分开描述。桌面制卡器导入独立胶卷文件，勾选装到卡上的风格；首次设置之后，增添胶卷不必重复机身设置。机身拨轮选胶卷，Canon CR2 留在 DCIM，另存的胶片 JPEG 来自 RITUAL 目录；屏幕预览、快速分享与最高像素输出明确区分。以 **5D II** 为例，指南把 Print 标为 **5616×3744**、耗时数分钟，另有较小档位；“Full”这个名称在该机型并非最大像素。

指南还说明后台显影、部分机型关机后下次续做，以及重负载可能报错。这是作者对产品行为的描述。我没有在指南中找到足以复核的源码提交、胶卷文件格式或算法许可证，也无法由指南判断是直接使用未压缩图，还是解码过已有 JPEG。可以借鉴清晰的尺寸、等待和状态提示；不能使用其商业风格文件、复刻内部算法，或把针对 Canon 的制卡、关闭和恢复步骤改个机名用在 E-P5。

## Soup Engine：要区分两个图像来源

以下是 **5D Classic** 端的实现，不推及仓库里的其他机型。作者将这版标为 beta，默认来源为 JPEG。每个风格是一份卡上 `ML/FILM/*.fs` 文本配方；UI 枚举文件、按名称保存选择，风格标签不自动修改相机 ISO。配方含主曲线、逐通道曲线及其他参数；RAW 与 JPEG 路径可明确使用不同参数。它不是把任意下载的 `.cube` 原样放到卡上。[5D 作者说明](https://github.com/jiijii0/soup-engine/blob/38f4d88165199e8b78577bc0c1b774ff541b01a4/Canon-EOS-5D/README.md) · [风格格式与两条路径](https://github.com/jiijii0/soup-engine/blob/38f4d88165199e8b78577bc0c1b774ff541b01a4/Canon-EOS-5D/src/stocks/README.md)

- `develop_one` 按图像来源分派。默认 `develop_preview` 读取 CR2 内嵌的 Canon JPEG（源码注明这台机身为 2496×1664），解码、调色、再编码 `.FLM.JPG`。这条路包含第二次有损压缩，不能拿作 E-P5 **4608×3456、首次 JPEG 编码前套 LUT** 的依据。[来源分派](https://github.com/jiijii0/soup-engine/blob/38f4d88165199e8b78577bc0c1b774ff541b01a4/Canon-EOS-5D/src/ml/payload/film.c#L2962) · [JPEG 路线](https://github.com/jiijii0/soup-engine/blob/38f4d88165199e8b78577bc0c1b774ff541b01a4/Canon-EOS-5D/src/ml/payload/film.c#L2334)
- 可选 `develop_raw` 从传感器数据起步，经暂存、分带处理和软件 JPEG 编码；作者提醒 RAW 路线较慢，部分针对完整 RGB 编写的风格参数不适用。代码将工作内存按最坏尺寸模式估算，而不是简单假定缩图一定占用更少。E-P5 可以借用按实际输入及工作区核算成本的方法，不能直接使用其 CR2 读取器或色彩系数。[RAW 显影调用](https://github.com/jiijii0/soup-engine/blob/38f4d88165199e8b78577bc0c1b774ff541b01a4/Canon-EOS-5D/src/ml/payload/film.c#L2922) · [分带流水线及工作区估算](https://github.com/jiijii0/soup-engine/blob/38f4d88165199e8b78577bc0c1b774ff541b01a4/Canon-EOS-5D/src/engine/pipeline.c#L30)
- `se_watch` 在后台扫描，`se_hold_develop` 条件不合适时暂缓；以同名旁存文件帮助跨启动识别已处理帧。名称能定位输出，但不能单凭名称认定写入完整。E-P5 导出/队列应绑定 RAW 身份、槽位和风格内容哈希，临时写入、完整校验后再发布结果。[后台任务](https://github.com/jiijii0/soup-engine/blob/38f4d88165199e8b78577bc0c1b774ff541b01a4/Canon-EOS-5D/src/ml/payload/film.c#L3126)

## M-Film：卡文件与合作式显影最值得参考

M-Film 源自 EOS M；其他机型的状态从能编译到实际完成功能测试不等，作者要求查逐机型测试表。它的移植接口 `fos_port_*` 把显示、按键、计时、内存和文件访问隔开，机身和电脑模拟器各有实现；桌面 Darkrooms 是另一个闭源项目。[移植接口](https://github.com/HNGSeries/mfilm-canon-film-simulation/blob/e76587c6eed9d894f7cc6be5021924b73e908ab7/PORTING.md) · [已测范围](https://github.com/HNGSeries/mfilm-canon-film-simulation/blob/e76587c6eed9d894f7cc6be5021924b73e908ab7/TESTING.md)

- 机内暗房分片读取 CR2，重建颜色后转换到线性 sRGB；其格点使用 Cineon 坐标、**33³ RGB8**、四面体插值。`ST_BIG` 的成片可以按行送入软件 JPEG 编码器。这是从 RAW 开始做一份新的 JPEG；传感器压缩解码与先解码一张有损 JPEG 再压缩不同。不能据此推断任何档位都保持传感器全像素。[格点和插值](https://github.com/HNGSeries/mfilm-canon-film-simulation/blob/e76587c6eed9d894f7cc6be5021924b73e908ab7/ml-dev/filmos/fos_dev.c#L147) · [按行编码](https://github.com/HNGSeries/mfilm-canon-film-simulation/blob/e76587c6eed9d894f7cc6be5021924b73e908ab7/ml-dev/filmos/fos_dev.c#L2392)
- `LOOK%02d.LUT` 是它的风格**缓存格式**。`lut_load` 检查文件头 `FOL1`、风格/模型参数标识和格点字节读取长度；未命中可分批生成。这个标识校验的是参数身份，不是表内容的强校验。作者的导入素材脚本说明外部 LUT 以普通 sRGB 图片为输入；这与机内缓存的编码约定不是一回事。E-P5 不应直接读取这种二进制或自行假定未知 `.cube` 为 sRGB。[缓存格式](https://github.com/HNGSeries/mfilm-canon-film-simulation/blob/e76587c6eed9d894f7cc6be5021924b73e908ab7/ml-dev/filmos/fos_dev.c#L208) · [外部表来源与输入域](https://github.com/HNGSeries/mfilm-canon-film-simulation/blob/e76587c6eed9d894f7cc6be5021924b73e908ab7/ml-dev/films/filmluts.py)
- `fos_dev_step(job,budget_ms)` 分时推进读入、解码、颜色处理和写文件；按帧记录耗时，并在结束/失败时关闭句柄、释放工作区。这能作为 E-P5 把长操作移出快门任务的接口参考。它不证明 E-P5 上相应 YCC 缓冲区归谁、何时可写或怎样同步 DMA 缓存。[步进状态机](https://github.com/HNGSeries/mfilm-canon-film-simulation/blob/e76587c6eed9d894f7cc6be5021924b73e908ab7/ml-dev/filmos/fos_dev.c#L2443) · [资源清理](https://github.com/HNGSeries/mfilm-canon-film-simulation/blob/e76587c6eed9d894f7cc6be5021924b73e908ab7/ml-dev/filmos/fos_dev.c#L1811)

Soup Engine 与 M-Film 的仓库均有 [Soup GPL v2](https://github.com/jiijii0/soup-engine/blob/38f4d88165199e8b78577bc0c1b774ff541b01a4/LICENSE) / [M-Film GPL v2](https://github.com/HNGSeries/mfilm-canon-film-simulation/blob/e76587c6eed9d894f7cc6be5021924b73e908ab7/LICENSE)。本次只核对实现，没有移入其源码、胶卷数据或二进制；若以后采用外部 LUT，须单独核对该素材的作者与再分发许可，不能用宿主代码的许可证替代。

## 落到 E-P5 工具和机内后端

1. **桌面库负责导入，卡包负责交付。** 在 [ep5studio](../ep5studio/) 保留源文件身份、输入域、风格名和许可备注；给每个分配的槽显示预览、格点缩减及量化误差。三维预览与双轴色度近似分别标识；有多个可选风格不等于当前官方 1.8 已能读卡。对照[格式约定](LUT_FORMAT_DESIGN.md)。
2. **首次安装和换风格是两种操作。** 未来后端只接受已定义的有界数据文件，核对版本、槽号、通道次序、长度与完整性之后才切换表；拍摄任务开始时保留该表身份直到完成。缺卡、拔卡、坏表或内存不足时，保证普通拍照与 ORF，报告未套用效果。桌面导出不需要改写可刷 BIN。在 [E-P5 运行时审计](LUT_RUNTIME_AUDIT.md)确认实际文件接入和生命周期以前，不把文件导出称为机身已安装。
3. **按照片验收一次压缩。** E-P5 的目标仍是用全幅中性输入做色彩处理后交回原厂 JPEG；要验证 4608×3456 主 JPEG、完整同次 ORF、关闭后与原厂一致。若另做旁存后台显影，应说明是否使用原始 ORF、原厂全幅缓冲或已压缩预览。用同一份 ORF 的机内重显影对照，避免把重拍曝光、针孔原效果、主机预览或二次压缩误算成 LUT 的改色能力。[已识别 ART 槽与共享表边界](ART_SLOT_AUDIT.md)
