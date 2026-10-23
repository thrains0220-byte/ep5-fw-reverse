#!/usr/bin/env python3
"""计算 E-P5 v1.8 `FUN_4058A207` 的 AF 驱动步数上限（可复现，替代手工估算）。

第二十一轮反编译要点（工程 mn103_full，函数 @ 0x4058A207）：

    thr  = 阈值（低于它不动作）
    cnt  = 每步分母
    base = 基数
    cap  = 上限（模式 3 的 step 6/3/5 → 0x6CC；step 4 → 0x1C20）
    RANGE= 0x800000（量程上限）

    steps  = (param2 - thr) // (cnt + base)
    steps2 = (RANGE  - thr) // (cnt + base)
    eff    = min(cap, steps2)          # 真正生效的上限
    out    = min(eff, steps)

⇒ **真瓶颈是 min(cap, steps2)**：多数分支里 steps2 比 cap 小，
   这就是「把 cap 抬到 0xFFFF 只对 step==3 有增益」的原因。

用法:
    python tools/af_cap_effect.py
    python tools/af_cap_effect.py --range 0x7fffffff
"""
import argparse

MODE3 = "mode3"
MODE2 = "mode2"

# (mode, step, thr, cnt_flag1, cnt_flag0, cap)
BRANCHES = [
    (MODE3, 6, 0x340, 0x1313, 0x1037, 0x6CC),
    (MODE3, 3, 0x340, 0x0C66, 0x098A, 0x6CC),
    (MODE3, 4, 0xA40, 0x03D1, 0x03D1, 0x1C20),
    (MODE2, 5, 0x190, 0x16E4, 0x1267, 0x6CC),
    (MODE2, 3, 0x190, 0x1267, 0x0FCD, 0x6CC),
]
BASE = {MODE3: 0x177, MODE2: 0x02F}


def eff_cap(cap, rng, thr, cnt, base):
    steps2 = (rng - thr) // (cnt + base)
    return min(cap, steps2), steps2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", type=lambda x: int(x, 0), default=0x800000,
                    help="量程常量（默认 0x800000）")
    ap.add_argument("--cap", type=lambda x: int(x, 0), default=None,
                    help="覆盖 cap（默认按各分支原值）")
    args = ap.parse_args()

    print("E-P5 v1.8 FUN_4058A207 —— AF 驱动步数上限")
    print("RANGE = 0x%X" % args.range)
    print()
    hdr = ("%-6s %-5s %-8s %-8s %-9s %-9s %-9s %-8s %s"
           % ("mode", "step", "thr", "cnt", "量程上限", "原cap", "原生效",
              "新生效", "增益"))
    print(hdr)
    print("-" * len(hdr))
    for mode, step, thr, c1, c0, cap in BRANCHES:
        base = BASE[mode]
        for flag, cnt in (("flag=1", c1), ("flag=0", c0)):
            e_old, s2 = eff_cap(cap, args.range, thr, cnt, base)
            newcap = args.cap if args.cap is not None else 0xFFFF
            e_new, _ = eff_cap(newcap, args.range, thr, cnt, base)
            gain = "-" if e_new == e_old else "+%.0f%%" % (
                (e_new - e_old) * 100.0 / e_old)
            print("%-6s %-5d 0x%-6X 0x%-6X %-9d 0x%-7X %-9d %-8d %s"
                  % (mode, step, thr, cnt, s2, cap, e_old, e_new, gain))
    print()
    print("说明：'原生效' = min(cap, 量程上限)，即当前固件实际允许的最大 AF 步数；")
    print("      '新生效' = 把 cap 抬到 0xFFFF 后的值；'增益' 为空表示量程公式才是瓶颈。")
    print()
    print("u32 溢出参考：输出按 steps * 0x1e 存 u32 => steps <= %d"
          % (0xFFFFFFFF // 0x1E))
    print("              返回值 steps * 600 (int) => steps <= %d"
          % (0x7FFFFFFF // 600))


if __name__ == "__main__":
    main()
