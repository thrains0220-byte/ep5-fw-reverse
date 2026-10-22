# LENS_INFO 结构的自描述布局 与 AF 参数定位（第十四轮补充）

> 日期：2026-10-22
> 基线：E-P5 v1.8 块 0（`decoded/00_0100_402c0020.decoded.bin`，基址 `0x402C0000`）
> 方法：利用固件**自带的调试转储字符串**反推 `LENS_INFO` 结构字段布局。
> 性质：**观察（静态）**。

---

## 0. 结论

1. **固件里有一个把 `LENS_INFO` 结构逐字段打印出来的调试转储函数**，
   它的格式串完整列出了结构体的每个字段名与类型 ——
   **这等于固件自己把镜头信息结构的字段表给了我们。**
2. AF 相关字段分成 6 组：
   `LENS_INFO_AF_CON` / `LENS_INFO_IS` / `LENS_INFO_LAF` / `LENS_INFO_AF` /
   `LENS_INFO_DIST` / `LENS_INFO_DISTORTION`。
3. **`LENS_INFO_LAF` 里有一个指针数组 `af_data_pos[%d]`** —— 这就是
   「每镜头 AF 参数数组」的挂载点（AF 数据本体在 `af_data_pos[i]` 指向处）。
4. 镜头子系统周边的 6 张表**全部指向 mask ROM（`0x7E1Exxx`–`0x7E1Fxxx`）**
   ⇒ **每镜头 AF 调校参数在机身 ROM 里，固件补丁无法改写。**

---

## 1. LENS_INFO 结构的字段清单（固件自述）

来源：块 0 字符串区 `0x405EC800`–`0x405ED400`。

### 1.1 顶层子结构（按转储出现顺序）

| 字段名 | runtime | 说明 |
|---|---|---|
| `LENS_INFO_EZ` | `0x405EC800` | 电动变焦 |
| `LENS_INFO_PRIVATE` | `0x405EC81D` | 厂商私有 |
| `LENS_INFO_PRIVATE_STATE` | `0x405EC841` | |
| `LENS_INFO_LENS_OIS` | `0x405EC86B` | 镜头防抖 |
| `LENS_INFO_ENABLE` | `0x405EC8FF` | |
| `LENS_INFO_CURRENT_CONSUMPTION` | `0x405EC96C` | |
| `LENS_INFO_ALL_DATA` | `0x405EC9E6` | |
| `LENS_INFO_STATE` | `0x405ECA0B` | |
| `LENS_INFO_CHARACTER` | `0x405ECB47` | |
| `LENS_INFO_CHARACTER_ZM` | `0x405ECC7E` | 变焦倍率特性 |
| `LENS_INFO_RESERVED` | `0x405ECD77` | |
| `LENS_INFO_MAKERNOTE` | `0x405ECD94` | |
| `LENS_INFO_SHADING` | `0x405ECE17` | 暗角 |
| `LENS_INFO_DISTORTION` | `0x405ECE37` | 畸变 |
| `LENS_INFO_FOURTHIRDS` | `0x405ECEFD` | |
| `LENS_INFO_AF_CON` | `0x405ECF3D` | **AF 常量** |
| `LENS_INFO_IS` | `0x405ECF4F` | **防抖常量** |
| `LENS_INFO_LAF` | `0x405ED030` | **镜头 AF 数据** |
| `LENS_INFO_LAF_CON` | `0x405ED151` | |
| `LENS_INFO_AF` | `0x405ED17A` | |
| `LENS_INFO_DIST` | `0x405ED188` | 畸变系数 |

### 1.2 AF / IS 常量组（`LENS_INFO_AF_CON` 与 `LENS_INFO_IS` 同构）

| 字段 | 含义（据名） |
|---|---|
| `flact_k0` / `flact_k1` / `flact_k2` | 实际焦距相关的 3 档系数 |
| `lat_mag_k1` / `lat_mag_k2` | 横向放大率系数 |
| `obj_princ_k0` / `k1` / `k2` | 物距/主点系数 |
| `ld_inf` | 对焦无穷远值 |

### 1.3 镜头 AF 数据组（`LENS_INFO_LAF`）★

| 字段 | runtime | 含义 |
|---|---|---|
| `min_pulse[%2d]` | `0x405ED03F` | 最小驱动脉冲（每档） |
| `max_fspeed[%2d]` | `0x405ED053` | |
| `min_fspeed[%2d]` | `0x405ED067` | |
| **`af_data_pos[%d]`** | `0x405ED07B` | **每镜头 AF 参数数组指针** |
| `vh.af_c[%d]` / `vh.af_u_d[%d]` / `vh.af_l_r[%d]` | `0x405ED08F` 起 | 垂直向 AF 校准向量（上/下、左/右、中心） |
| `vl.af_c/af_u_d/af_l_r` | `0x405ED0C1` 起 | |
| `vv.af_c/af_u_d/af_l_r` | `0x405ED0EB` 起 | |
| `hk.af_c/af_u_d/af_l_r` | `0x405ED115` 起 | |
| `LENS_LAF_DISABLE` | `0x405ED13F` | |

> 四组向量前缀 `vh / vl / vv / hk` 的含义**未判定**
> （推断：`vh`=vertical、`vl`/`vv`=水平两个方向、`hk`=水平？）。
> **保留为未知。**

### 1.4 畸变系数组（`LENS_INFO_DIST`）

`dis_lc_0[%2d]` / `dis_lc_1[%2d]` / `dis_lc_2[%2d]` / `dis_r[%2d]` / `dis_m[%2d]` /
`dis_e_0[%2d]` / `dis_e_1[%2d]` / `dis_e_2[%2d]` @ `0x405ED1A5`–`0x405ED211`

### 1.5 其它

`LENS_INFO_SHADING`：`index[%x] = ` @ `0x405ECE2A`
`LENS_INFO_CHARACTER`：`focal_length_w / focal_length_t / serial_number / firm_version /
zm_enc_div / zm_prm_num / fc_enc_div / dis_zm_enc_num / dis_fc_enc_num / dis_zm_num`
`LENS_INFO_CHARACTER_ZM`：`zm_num[%2d]` / `focal_length_center` / `av_official[0..1]` /
`av_effect[0..1]` / `af_judge` / `ld_max_min` / `dst_min`
`LENS_INFO_LAF`：`valid_pls_num` / `pulse` / `state_ez` / `speed_ez` / `state_time` /
`status_private` / `laf_dis_m[%d]`

---

## 2. 镜头子系统周边表的归属判定

在 `0x405E8000`–`0x405F0000`（LENS_INFO 主表 `0x405E8EE0` 之后）找到 **6 张
mask ROM 指针数组**：

| runtime | 项数 | 目标 ROM 区间 |
|---|---|---|
| `0x405EE4DC` | 20 | `0x7E1EFAE6`–`0x7E1F06E8` |
| `0x405EE828` | **100** | `0x7E1F162B`–`0x7E1F23EC` |
| `0x405EEAB4` | 34 | `0x7E1F2D1C`–`0x7E1F2D83`（大量重复默认值） |
| `0x405EEE6C` | 46 | `0x7E1F4B55`–`0x7E1F53B4` |
| `0x405EEF58` | 24 | `0x7E1F667B`–`0x7E1F6696` |
| `0x405EF0B4` | 25 | `0x7E1F6A4C`–`0x7E1F6C37` |

⇒ **观察**：这些表**全部指向机身 mask ROM**。

### 结论

> **每镜头的 AF 调校参数（`af_data_pos[]` 指向的内容、以及 6 张表）
> 全部存放在机身 mask ROM 中。**
>
> ⇒ 对 2018-12-18 松下镜头 AF 修复而言，
> **「固件补丁能否改写每镜头 AF 参数」这一问题的答案是：不能**
> （除非固件只是改"用哪一组参数"的索引/开关，而不改参数本体）。
>
> 这把 AF 修复的落点收窄到：**块 0 内既有代码的行为改动**
> （新分支 / 改常量 / 改选择哪一组参数），
> 而不是"往数据表里加一组参数"。

> 与 `evidence/af_fix_2018/af_fix_block_scope.md` §6 的候选清单对照：
> 候选 #2「每镜头 AF 参数组新增一组」**降级为不可行**（数据在 ROM）；
> 候选 #1「AF 控制流程中的新分支」与候选 #3「镜头 I²C 应答处理」**升为首选**。

---

## 3. 仍未解决

| # | 问题 | 现状 |
|---|---|---|
| 1 | 打印 `af_data_pos[%d]` 的函数在哪 | **未定位**。该字符串与 LENS_INFO 主表地址 `0x405E8EE0` 在块 0 内均**无 4 字节直接引用**；推断为「基址寄存器 + 16 位位移」寻址，但候选基址扫描因 2 字节模式过于常见而无法区分（见 `tools/find_addr_base.py` 的尝试与局限） |
| 2 | `af_data_pos[]` 的项数与索引语义 | **未知** |
| 3 | `vh/vl/vv/hk` 四组 AF 向量的物理含义 | **未知** |
| 4 | 「每镜头 AF 参数组」是否就是 cmdada 说的 12 组 | **未证实**（E-M10 侧为 ~12 组，E-P5 侧无对应计数证据） |

### 下一步的确切做法

1. 用 Ghidra 的 **xref 视图**（而非字符串匹配）打开 `0x405ED07B`，
   看是否有 `DATA`/`computed` 引用（本项目已证实 `art_*` 字符串是 0 引用，
   但这些 `LENS_INFO` 字符串被实际打印，**必然有引用**——只是寻址形式特殊）。
2. 扫描块 0 内所有 `mov.l` 立即数落在 `0x405C0000`–`0x405F0000` 的指令，
   逐条还原「基址 + 位移」，反推真正的基址寄存器值
   （本轮 `find_addr_base.py` 因 2 字节模式频次过高而失效，
   需要改成**按指令解码**而非按字节统计）。
3. 定位到打印函数后，从其伪代码直接读出 `LENS_INFO` 各字段偏移，
   即可确定 `af_data_pos[]` 在结构中的偏移与项数。

---

## 4. 复现

```sh
# LENS_INFO 字段清单
python tools/strings_in_range.py --blk decoded/00_0100_402c0020.decoded.bin \
    --lo 0x405EC800 --hi 0x405ED400

# 镜头子系统周边的 mask ROM 指针数组
python tools/find_ptr_ranges.py --blk decoded/00_0100_402c0020.decoded.bin \
    --lo 0x7E000000 --hi 0x7F000000 --min-run 4
# （注意：该脚本全块扫描较慢，建议配合 grep 缩小范围）

# 基址反解尝试
python tools/find_addr_base.py --blk decoded/00_0100_402c0020.decoded.bin \
    --targets 0x405ED07B,0x405ECF3D,0x405ED17A,0x405ED188
```
