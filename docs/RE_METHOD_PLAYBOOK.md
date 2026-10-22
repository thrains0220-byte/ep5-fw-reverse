# 奥林巴斯固件逆向方法论手册（可复用）

> 来源：本项目 2026-10-22 的六轮实战（E-P5 / E-P5 1.8 / E-M5 / E-PM2 / 社区改机归档）
> 目的：把踩过的坑与有效手法固化下来，供后续会话直接复用，不必重走弯路。

---

## 0. 奥林巴斯固件的四个"性格"

| 特征 | 事实 | 逆向含义 |
|---|---|---|
| **容器自描述** | 每块 32 字节头 + 混淆 payload + 32 字节尾，头尾前 28 字节相同 | 可以**完全自动解析**，不需要猜格式 |
| **校验不是 CRC** | 加法 `sum32`（`-Σ(u32 LE)`） | **改完能自己重算**，这是能否改固件的决定性因素 |
| **指令集是 MN1030/MN103S** | 16 位小端 RISC，Ghidra 官方**没有**后端 | 必须自建 objdump 或装第三方 SLEIGH 模块 |
| **块内字符串不可立即数寻址** | 62,167 条字符串里**只有 1 条**被 `fc <imm32>` 直接引用 | **"搜立即数找字符串"这条路对整块固件无效** |

---

## 1. 标准流程

### 阶段 0：容器（1 次投入，永久复用）

```sh
python tools/oly_container.py <firmware.BIN> --out decoded/
# 自检：roundtrip_identical == true，且 4/4 块 checksum_valid
```

要点：
- `decode()` / `encode()` 互逆；**任何修改后都必须走 `encode()` 重混淆**再重算 sum32。
- `replace_payload(block, new_payload)` 会自动重算尾校验和 —— 改固件的入口。
- 块 0 = 代码（MN103），块 1 = 多语言+字体，块 2 = 6-bit 加密区，块 3 = 叠加位图。
- **块 0 的容器地址 ≠ 一定等于运行时基址**；E-P5/E-P3/E-PM2 是 `0x402C0000`，
  E-M5 是 `0x902C0000`（容器地址）。**先验证再使用**。

### 阶段 1：指令集与反汇编

```sh
# WSL(Alpine) 里自建 binutils（仓库 tools/build_mn103_objdump.sh）
apk add --no-cache build-base zlib-dev
# Alpine 没有 xz 包 => 用 .tar.gz 而不是 .tar.xz
```

**更好的选择：Ghidra + 第三方 SLEIGH 模块**（本项目最终采用）
- 模块：https://github.com/txt231/GhidraMn10300
- Olympus 调用约定（A0/A1=指针，D0/D1=整数，栈参数 `(12+imm,sp)`，返回指针 A0）：
  https://github.com/cmdada/em10-fw/tree/main/tools/ghidra （`mn103-olympus.cspec`）
- `mn103-call.patch` 修复 `call f,[regs],imm` 的保存寄存器恢复 —— **必须打**。

**Ghidra 12.x 的两个坑**（本项目实测）：
1. **没有 `<proc>/<Module>.ldefs`**：处理器注册只靠 `data/languages/*.ldefs` 里的
   `processor=` 属性。照搬旧版布局会导致 Processor 扩展点里看不到语言。
2. **地址空间必须 32 位**：`mn103.sinc` 保留 `define space ram ... size=4`
   （镜像装在 `0x402C0000`，代码里有 32 位绝对地址）。语言 ID 仍可登记为
   `MN103:LE:16:default`（"16" 描述 CPU 位宽），另加 `MN103:LE:32:default` 别名。

**批量建函数**（裸二进制没有入口点，Ghidra 自动分析会得到 **0 个函数**）：
```java
// 全镜像线性反汇编 + 在所有 CALL 目标处建函数
DisassembleCommand cmd = new DisassembleCommand(set, null, false);
cmd.enableCodeAnalysis(false);
cmd.applyTo(currentProgram, monitor);
// 再遍历指令，把所有 in-block CALL 目标 createFunction(...)
```
实测：块 0 15.7 MB → 6,488,149 条指令 / 56,984 个函数 / 约 60 秒。

**与 GNU objdump 交叉验证**（务必做）：同一窗口两条工具的指令边界与语义必须逐条一致。
本项目 77/77 一致，0 差异。

### 阶段 2：定位子系统

**不要用"搜立即数找字符串"** —— 见 §0。有效锚点按优先级：

| 锚点 | 怎么用 | 本项目实例 |
|---|---|---|
| **数据结构标记字符串** | 找 `<结构>_SIZE` 之类的标记，向前找定长记录数组 | `"LENS_INFO SIZE"` → 106 条镜头主表（0x405E8EE0） |
| **RAM 全局变量** | 先用反编译器找到关键全局，再全库搜它的 32 位引用 | `iRam605fcd3c` → 9 处引用全在一个 4 KB 簇 → 定位整个艺术滤镜子系统 |
| **数值特征** | 例如"某函数只含 {10,50} 两个比较常量" | `FUN_4078846d` → 艺术效果 ID 全局 |
| **跨机型同构** | 同一代码库的机型会有结构相同的特征 | E-P5 与 E-PM2 的候选列表一一对应 |

**"只含 N 个比较常量的函数"是极强的信号**：真实业务分派函数的比较常量集非常小，
而通用库函数的比较常量集很大。

### 阶段 3：语义差分（跨版本找补丁）

**前提：必须先有"修复前"基线。** 本项目拿到基线的路径（按优先级）：
1. **xdel.ru** `original/` 与 `pre_fix/` —— 含同机型的历史版本，**比 Wayback 全**
2. Wayback 的 `dl01.om-digitalsolutions.net/OMDS/FIRMWARES/0001/<model>/`
   —— **只存最新一版**（本项目 5 域名 / 21,038 URL 全量普查确认）
3. 官方直链 —— 403（CloudFront 签名失效）

**差分四级递进**（本项目实测有效）：

| 级别 | 方法 | 本项目结果 |
|---|---|---|
| 1 | 逐字节 diff | ❌ 三年期固件 23% 字节变化、35 万跨度，**完全不可用** |
| 2 | **字符串锚点对齐** | 331 万 → 15.5 万残差字节（**21× 改善**） |
| 3 | **全块 diff**（先定"在哪个块"） | ✅ 立刻把范围收窄到块 0 |
| 4 | **归一化函数集合语义差分** | ✅ 定位到自动找出版本常量 `0x2202→0x2300` |

**归一化规则**（决定成败）：
- 分支/调用目标 → `T`（重定位噪声）
- 指向**镜像自身**的地址 → `A`（代码/数据重排噪声）
- **RAM 全局 (0x60xxxxxx) 与 mask ROM (0x7Exxxxxx) 原样保留** ← 关键！
  这两类地址跨版本稳定，且能标识功能（AF/镜头相关函数会引用它们）

**配对策略**：不要对全部函数做 O(n²) 相似度配对（difflib 会跑到天荒地老）。
改为**先按"引用的稳定地址集合"分组**（O(n)），只在同组内配对。

**必须做校准**：差分工具要能自动找出版本号常量变化，才算可信。
本项目三次独立校准：社区补丁偏移与 fishcu 记录吻合 / 容器往返 SHA-256 一致 /
自动找出 `0x2202→0x2300`、`0x1501→0x1600`。

### 阶段 4：补丁 → 刷机

1. 改 decoded payload（等长，16 字节对齐）
2. `encode()` 重混淆 → 重算尾校验和 → 重打包
3. 写 SD 卡（奥林巴斯走 `DCOLYMP\<model><ver>.BIN` 目录 + 文件名）
4. **无实机 = 未验证**。务必在报告里写清楚"只到静态层面"。

---

## 2. 本项目沉淀的具体"坑"

| 坑 | 症状 | 解法 |
|---|---|---|
| **Ghidra 找不到语言** | Processor 扩展点里没有新语言 | 12.x 只认 `data/languages/*.ldefs` 的 `processor=` 属性 |
| **地址空间 16 位装不下** | 导入后地址全错 | `size=4`；语言 ID 仍可写 16 |
| **Ghidra 自动分析得 0 个函数** | 裸二进制没有入口点 | 自写批量线性反汇编 + CALL 目标建函数 |
| **`fc` 搜字符串搜不到** | 62167 条字符串只有 1 条有引用 | 改用 RAM 全局 / 结构标记字符串 / 数值特征 |
| **bsdtar 解 RAR 数据损坏** | header/trailer mismatch | RAR 内含 bsdtar 不支持的过滤器，需真 `unrar` |
| **Alpine 没有 xz 包** | `tar -xf *.tar.xz` 失败 | 改用 `.tar.gz` |
| **PowerShell 吞掉 `$(nproc)`** | 命令被本地解释 | 写进 `.sh` 文件再由 bash 执行 |
| **`_readerthread` UnicodeDecodeError** | subprocess 读工具的非 UTF-8 输出 | `encoding="utf-8", errors="replace"` |
| **函数边界只是近似** | 数据区被误判为代码 | CALL 目标推导的边界在数据区不可靠；关键处用已知入口播种 |
| **`decoded/` 目录已存在** | `mkdir exist_ok=False` 报错 | 先判 manifest.json 是否存在 |

---

## 3. 工具清单（本仓库）

| 工具 | 作用 |
|---|---|
| `tools/oly_container.py` | 容器解析/解混淆/重打包/补丁（`replace_payload`） |
| `tools/decode_any.py` | 任意机型固件解码 |
| `tools/ep5_lens.py` | 镜头 ID 比较链精确还原 + LENS_INFO 主表提取 + 跨版差分 |
| `tools/lens_compare.py` | 跨机型/跨版本镜头结构语义对照 |
| `tools/blockdiff.py` | 全块差分（判定修复落在哪个块） |
| `tools/align_diff.py` / `align_pages.py` | 字符串锚点对齐差分 + 残差页分布 |
| `tools/str_delta.py` | 版本间字符串增减 |
| `tools/semdiff.py`~`semdiff4.py` | 归一化函数集合语义差分（4 种配对策略） |
| `tools/cmp_hist.py` | 比较常量频次差分 |
| `tools/find_art_funcs.py` / `find_art_global.py` / `find_art_reg.py` | 艺术滤镜子系统定位 |
| `tools/find_lens_tables.py` / `find_ptr_tables.py` | 数据表搜索 |
| `tools/patched_batch.py` / `patched_diff.py` | 社区改机归档逐字节差分 |
| `tools/gen_art_evidence.py` | 证据 JSON 生成 |
| `tools/ghidra/*.java` | 11 个 GhidraScript（反编译/范围反编译/全局引用/调用者/归一化导出/全量建函数…） |

---

## 4. 给后续会话的十条提醒

1. `art_*` 这类名字是**残留符号名表**，**零引用**，不能用来定位代码。
2. 找到**关键 RAM 全局**比找到字符串有用得多 —— 全局一找到，整个子系统就浮出来了。
3. **先用全块 diff 确定"在哪个块"**，再在块内做精细差分。
4. 跨版本 diff 前先确认有"修复前"基线；**xdel.ru 比 Wayback 全**。
5. 差分结果必须**自动找出版本常量变化**才算校准通过。
6. 归一化时**保留 RAM/ROM 地址**，遮蔽它们会丢掉全部功能信息。
7. Ghidra 12.x 装 SLEIGH 模块有两个固定坑（见 §2）。
8. 裸二进制没有入口点，**必须自写批量反汇编**。
9. 社区 patched 归档是**解锁功能的字节级先例**，比从零推导快一个数量级。
10. 每条结论都要分清**观察 / 推断 / 未知**，并注明证据来源与覆盖边界。
