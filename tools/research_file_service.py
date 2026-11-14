"""Map the E-P5 stock file-service veneers (open/close/read/write/...).

Read-only research on the decoded MAIN. Identifies each service wrapper by its
message number and argument frame so a diagnostic branch can reuse the stock
write service to log observations to SD. No camera I/O, no firmware output.
"""
from pathlib import Path
import struct

BASE = 0x7e101020
ROOT = Path(__file__).resolve().parents[1]
d = (ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin").read_bytes()

start = 0x7e291400 - BASE
end = 0x7e291a00 - BASE
seg = d[start:end]

# message number loads: fc cd <imm32 LE> with imm in 0x10000..0x100ff
msgs = []
for i in range(len(seg) - 6):
    if seg[i] == 0xfc and seg[i + 1] == 0xcd:
        imm = int.from_bytes(seg[i + 2:i + 6], "little")
        if 0x10000 <= imm <= 0x100ff:
            msgs.append((BASE + start + i, imm))

# ret frames: df <mask> <n>
rets = []
for i in range(len(seg) - 3):
    if seg[i] == 0xdf:
        rets.append((BASE + start + i, seg[i + 1], seg[i + 2]))

print("message-number loads:")
for addr, imm in msgs:
    print(f"  {hex(addr)}  msg {hex(imm)}")
print("\nret frames (addr, mask, stack_bytes):")
for addr, mask, n in rets:
    print(f"  {hex(addr)}  mask {hex(mask)}  n={n}")

# For each message, find the enclosing function's ret (next ret after the msg load)
print("\nmessage -> enclosing ret frame:")
for addr, imm in msgs:
    after = [r for r in rets if r[0] > addr]
    if after:
        ra, mask, n = after[0]
        print(f"  msg {hex(imm)} @ {hex(addr)} -> ret {hex(ra)} mask {hex(mask)} n={n}")
