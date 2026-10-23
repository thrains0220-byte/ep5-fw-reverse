# 第二十四轮：★ 相机固件内置内存读写原语（`memdump` / `memload`）

> 日期：2026-10-24
> 性质：**关键发现**。这是「实机 dump mask ROM」这条路的**最短路径**。
> 证据：E-P5 v1.8 块 0 内的字符串池（运行地址 `0x40643xxx` 区间）

---

## 0. 一句话

> **E-P5 的出厂固件里自带一个文件系统调试 shell，其中 `memdump NAME ADR LEN`
> 能把任意内存地址写成 SD 卡上的文件，`memload NAME ADR [LEN]` 能把 SD 卡文件写进任意内存。**
> ⇒ 读 mask ROM **不需要拆机、不需要改固件**，只需要能进这个 shell。
> ⇒ 而且 `memload` 还意味着：**如果 `0x7Exxxxxx` 在运行时可写，
> 菜单描述符、滤镜参数块都可以直接改写** ——「新增滤镜」这条路可能被重新打开。

---

## 1. 发现经过

### 1.1 搜索词

在 E-P5 块 0 的字符串池里搜文件/SD 卡相关关键词时，命中一个完整的 **shell 帮助文本**：

```
0x40643926  'FileSystem Debug Command'
0x4064393F  '  mount         - mount FAT'
0x4064395B  '  umount        - power off'
0x40643977  '  format        - format FAT'
0x40643994  '  pwd           - print working dir'
0x406439B8  '  cd DIR        - change working dir'
0x406439DD  '  ls [-l]       - list dir entries'
0x40643A00  '  rm NAME       - remove file'
0x40643A1E  '  rmdir NAME    - remove dir'
0x40643A3B  '  mkdir NAME    - create dir'
0x40643A58  '  chmod [+w|-w] NAME  - change read-only attr'
0x40643A86  '  chmod [+h|-h] NAME  - change hidden attr'
0x40643AB1  '  chmod [+a|-a] NAME  - change archive attr'
0x40643ADD  '  cat NAME      - print contents of file'
0x40643B06  '  chdev [DEVNAME]        - change media (xd,cf,in,in2)'
0x40643B45  '  rawread LBA            - print contents of sector (LBA:dec)'
0x40643B83  '  rawread -c CLS SCT     - print contents of cluster (CLS,SCT:dec)'
0x40643BC6  '  memdump NAME ADR LEN   - dump memory into file (ADR:hex,LEN:dec)'
0x40643C09  '  memload NAME ADR [LEN] - load memory from file (ADR:hex,LEN:dec)'
0x40643C4C  '  perf          - performance check'
0x40643C70  '  dbginfo       - print debug info'
0x40643C93  '  help          - print this message'
```

### 1.2 命令名表（同区域）

```
0x40643839 'HH~mount'   0x40643842 'umount'   0x40643849 'format'
0x40643879 'rawread'    0x40643881 'memdump'  0x40643889 'memload'
0x406438A1 'hidden'     0x406438AB 'formatex' 0x406438BB 'dbginfo'
0x406438DE 'reboot'     0x406438E5 'dcfcopy'  0x406438ED 'mulsize'
0x406438FA 'dcfmnt'     0x40643901 'correct'  0x4064390D 'volinfo'
0x40643915 'filetest'
```

【观察】还有一整套**文件系统自检**代码（`filetest:: *** CREATE FILE ***` → `TESTFILE.BIN` →
`filetest:: *** FILE WRITE ***` → `fileif_fwite err.` → `filetest:: *** FILE READ ***`）
与 `FILE_CREATE_FILE` / `FAT_CHAIN_WRITE` / `FAT_FORMAT` / `FAT_MOUNT` 等命令名。

【观察】还有**第二套** `memdump` / `memload` 字符串，在 **SPC 服务协议**区
（容器地址 `0x410A4E47` / `0x410A4E57`，运行地址 `0x410A4E27` / `0x410A4E37`），
与 `spc_ctrl_*`、`spc cat : cat \SD_WLAN\CONFIG` 等字符串同区。

---

## 2. 为什么这条命令可能是**现成可用**的

【观察】E-P5 固件的**固件升级路径本身**就在读 SD 卡上的 `.BIN`：

```
0x405F20B0  '[firmup]File Init Err.'
0x405F20FF  '[firmup]...Binary file Hakken !!!!!'
0x405F2124  '[firmup]...read file_size ='
0x405F220C  '[firmup]file_mount/ start.'
0x405F225C  '[firmup]...FIRMUP_CARD_USR_ERROR'
```

⇒ 相机**自己**会 mount FAT、读 `.BIN`、写 flash。
⇒ **社区改机补丁本身就是被改过的 `.BIN`，而且能刷进去** ⇒
**E-P5 接受修改过的固件**（本项目 `tools/oly_container.py` 可重算校验和）。

---

## 3. 三条可选路线

| 路线 | 做什么 | 变砖风险 | 需要的额外工作 |
|---|---|---|---|
| **A** | 直接进 FileSystem Debug Command，`memdump ROM.BIN 0x7E452BD0 256` | **无**（不改固件） | ★ 找到这个 shell 的**入口/输入通道**（未定位） |
| **B** | 改固件：开机时把 `0x7E000000–0x7EFFFFFF` 写进 SD 卡 | 中（社区补丁有先例，但仍需回砖方案） | 找文件写 API + 找可插入的钩子点 + 重打包 |
| **C** | 先验证已有补丁：刷入 AF 步数上限 6 字节配方 | 中 | 已有配方（`patches/ep5_v1_8_af_unlock.json`） |

### 3.1 路线 A 的关键未知

【观察】**这个 shell 的分派代码不在 E-P5 块 0 里**：

- 块 0 内**没有任何指针**指向 `0x40643800–0x40643940` 这段字符串区；
- 同样地，`TESTFILE.BIN` / `filetest:: *** START ***` / `fileif_fwite err.` /
  `OLYMPUS DIGITAL CAMERA` 这些**必然被引用**的字符串，在块 0 里也搜不到任何
  u32 指针、`fc dc`+u32、高/低半字对、u24、PC 相对 32 位偏移。

【推断】字符串的引用**机制仍未确定**（可能指向另一个地址映射，或经由别的 CPU/ROM 间接寻址）。
⇒ 需要用 Ghidra 的**数据流/字符串引用分析**（而非字节搜索）定位。

### 3.2 路线 B 的关键未知

- 块 0 没有空闲空间 ⇒ 需要**等长覆盖**或复用既有代码；
- 可复用的既有代码已经确认存在：
  `FUN_407868FC(0x605FCA00, 0x7E5C9809, 0)` 就是「从 ROM 拷参数到 RAM」的现成调用。

---

## 4. 如果路线 A/B 都走不通，还有路线 D

【推断】**`memload` 意味着「运行时可写」**。若 `0x7Exxxxxx` 其实是可写 flash
（只是**不由固件更新下发**），那么：

- `memdump` → 把 ROM 读出来分析；
- `memload` → **把新的菜单描述符 / 滤镜参数块直接写进 ROM**，
  从而实现「录像 10 项」「新增滤镜变体」——而无需任何固件补丁。

⇒ **这会让「新增创意滤镜」从「判定不可行」变成「取决于 ROM 是否可写」。**
⇒ 这也是**最值得优先验证的一件事**（一条 `memload` 试写 + 回读比对即可判定）。

---

## 5. 需要实机确认的问题

| # | 问题 | 为什么重要 |
|---|---|---|
| 1 | 相机当前固件版本？ | E-P5 最高 1.8；老版本可能有不同的 shell 入口 |
| 2 | 能否读写 SD 卡（读卡器）？ | 三条路线都要 |
| 3 | 是否试过「卡刷」（按住 OK 开机进更新模式）？ | 路线 B/C 的前置操作 |
| 4 | 相机有没有 USB 调试/服务口？（机身或配件） | 路线 A 的可能输入通道 |
| 5 | 是否已有原厂 `.BIN` 备份？ | 回砖用 |

## 6. 本轮新增工具

| 工具 | 作用 |
|---|---|
| `tools/ghidra/Mn103FindXrefs.java` | 用 Ghidra 原生引用分析查「数据地址 → 代码引用」（字节搜索失效时的替代） |

（辅助脚本 `fw-work/find_hi_lo_ref.py`、`probe_ref_style.py`、`find_indirect_ref.py`
用于确定字符串引用机制，结论：**块 0 字符串在块 0 内找不到任何形式的引用**。）
