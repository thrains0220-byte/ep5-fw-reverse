#!/usr/bin/env bash
#
# 从官方固件镜像完整复现本仓库的派生结果。
#
#   1) 解混淆  → decoded/*.decoded.bin + manifest.json + strings.jsonl + leads.jsonl
#   2) 校验    → 往返一致（decode→encode 与源文件 SHA-256 相同）+ 4/4 块 sum32 校验
#   3) 反汇编  → disasm/*.txt（需要 MN103 objdump，见 tools/build_mn103_objdump.sh）
#
# 本仓库不含固件本体。需自行准备官方镜像：
#   OLY_E_108_1800_0000_0000.BIN
#   SHA-256 cc59a4e13b3bf6c46405bd396975cb9c93a7634b7a4a36822259b1fc498b5cfd
#
# 用法：
#   bash reproduce.sh /path/to/OLY_E_108_1800_0000_0000.BIN
#   bash reproduce.sh /path/to/fw.BIN --out /tmp/ep5-out --skip-disasm
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FW_SHA256="cc59a4e13b3bf6c46405bd396975cb9c93a7634b7a4a36822259b1fc498b5cfd"

IMAGE=""
OUT_DIR="${ROOT_DIR}/reproduce_out"
SKIP_DISASM=0

log() { printf '\033[1;34m[repro]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[repro]\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --out) OUT_DIR="$2"; shift 2 ;;
        --skip-disasm) SKIP_DISASM=1; shift ;;
        -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
        -*) die "unknown option: $1" ;;
        *) [ -z "${IMAGE}" ] || die "only one image path allowed"; IMAGE="$1"; shift ;;
    esac
done

[ -n "${IMAGE}" ] || die "usage: bash reproduce.sh <OLY_E_108_1800_0000_0000.BIN> [--out DIR] [--skip-disasm]"
[ -f "${IMAGE}" ] || die "firmware image not found: ${IMAGE}"

# ------------------------------------------------------------------- 0. 前置检查
command -v python3 >/dev/null 2>&1 || die "python3 not found"
log "python: $(python3 --version 2>&1)"

# ------------------------------------------------------------------- 1. 校验源文件
log "verifying source SHA-256"
ACTUAL_SHA="$(sha256sum "${IMAGE}" | cut -d' ' -f1)"
if [ "${ACTUAL_SHA}" != "${FW_SHA256}" ]; then
    die "SHA-256 mismatch
  expected ${FW_SHA256}
  actual   ${ACTUAL_SHA}"
fi
log "source SHA-256 OK: ${ACTUAL_SHA}"

# ------------------------------------------------------------------- 2. 解混淆 + 校验
[ -e "${OUT_DIR}" ] && die "output dir already exists: ${OUT_DIR} (remove it or pass --out)"
mkdir -p "${OUT_DIR}"

log "decoding container (scramble + checksum verification)"
python3 "${ROOT_DIR}/tools/oly_container.py" "${IMAGE}" \
    --out "${OUT_DIR}/decoded" \
    --expect-sha256 "${FW_SHA256}" \
    > "${OUT_DIR}/decode_report.json"

python3 - "${OUT_DIR}/decode_report.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
assert report["roundtrip_identical"] is True, "roundtrip failed"
for b in report["blocks"]:
    assert b["checksum_valid"] is True, f"checksum failed for block {b['index']}"
print(f"[repro] roundtrip_identical: {report['roundtrip_identical']}")
print(f"[repro] blocks verified: {len(report['blocks'])}/4 (sum32)")
for b in report["blocks"]:
    print(f"[repro]   block {b['index']} kind={b['kind']} "
          f"addr={b['header_address']} size={b['payload_size']}")
PY

# ------------------------------------------------------------------- 3. 反汇编
if [ "${SKIP_DISASM}" -eq 1 ]; then
    log "--skip-disasm given, stopping after decode+verify"
    exit 0
fi

OBJDUMP="${ROOT_DIR}/toolchain/binutils/objdump"
if [ ! -x "${OBJDUMP}" ]; then
    log "MN103 objdump not found, building it (first run only)"
    bash "${ROOT_DIR}/tools/build_mn103_objdump.sh" \
        || die "objdump build failed; re-run with --skip-disasm to skip disassembly"
fi

CODE_REL="decoded/00_0100_402c0020.decoded.bin"
[ -f "${OUT_DIR}/${CODE_REL}" ] || die "decoded block 0 missing: ${OUT_DIR}/${CODE_REL}"

mkdir -p "${OUT_DIR}/disasm"
log "disassembling (MN103, --insn-width=16)"

# 在 OUT_DIR 内以相对路径调用 objdump，使输出头部文件名与仓库内产物一致。
disasm_range() {
    local start="$1" stop="$2" out="$3"
    (
        cd "${OUT_DIR}"
        "${OBJDUMP}" -b binary -m mn10300 -D -z --insn-width=16 \
            --adjust-vma=0x402C0000 \
            --start-address="${start}" --stop-address="${stop}" \
            "${CODE_REL}"
    ) > "${out}"
    log "  wrote $(basename "${out}") ($(wc -l < "${out}") lines)"
}

# 区间与 disasm/ 中已提交的样本一一对应
disasm_range 0x402C0000 0x402C0400 "${OUT_DIR}/disasm/entry_0x402C0000.txt"
disasm_range 0x402F8800 0x402F8900 "${OUT_DIR}/disasm/memmap_table_0x402F8800.txt"
disasm_range 0x405BDF00 0x405BE120 "${OUT_DIR}/disasm/lens_info_dump_0x405BDF00.txt"
disasm_range 0x402CF190 0x402CF4A0 "${OUT_DIR}/disasm/lens_state_switch.txt"

# ------------------------------------------------------------------- 4. 汇总
log "done."
cat <<EOF

输出目录: ${OUT_DIR}
  decode_report.json            容器元数据 + 往返/校验结果
  decoded/*.decoded.bin         4 个反混淆块
  decoded/manifest.json         块级元数据
  decoded/strings.jsonl         全部字符串索引
  decoded/leads.jsonl           固件/版本/升级相关子集
  disasm/*.txt                  MN103 反汇编样本

对照：本仓库 report/逆向分析报告_E-P5_Ver1.8.md
EOF
