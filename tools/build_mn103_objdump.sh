#!/usr/bin/env bash
#
# 构建支持 mn10300 目标的 GNU objdump。
#
# 背景：发行版自带的 binutils（Debian/Ubuntu 2.38+）已经移除了 mn10300 后端，
# 而 Olympus PEN E-P5 / E-PL3 / E-M1 III 的主控是 Panasonic MN1030/MN103S。
# 因此必须自行编译 binutils 2.45 并指定 --target=mn10300-elf。
#
# 产物：toolchain/binutils/objdump  （本目录已在 .gitignore 中排除）
#
# 用法：
#   bash tools/build_mn103_objdump.sh
#   bash tools/build_mn103_objdump.sh --src-dir /path/to/binutils-2.45
#
set -euo pipefail

BINUTILS_VERSION="2.45"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/toolchain/src"
BUILD_DIR="${ROOT_DIR}/toolchain/build"
PREFIX_DIR="${ROOT_DIR}/toolchain/binutils"

log() { printf '\033[1;34m[build]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[build]\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --src-dir) SRC_DIR="$2"; shift 2 ;;
        --build-dir) BUILD_DIR="$2"; shift 2 ;;
        --prefix) PREFIX_DIR="$2"; shift 2 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------- prerequisites
command -v make >/dev/null 2>&1 || die "make not found"
command -v gcc  >/dev/null 2>&1 || die "gcc not found"
command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 \
    || die "curl or wget not found"
command -v tar  >/dev/null 2>&1 || die "tar not found"

# ---------------------------------------------------------------------- source
TARBALL="binutils-${BINUTILS_VERSION}.tar.xz"
TARBALL_PATH="${SRC_DIR}/${TARBALL}"
SRCDIR="${SRC_DIR}/binutils-${BINUTILS_VERSION}"

if [ ! -d "${SRCDIR}" ]; then
    mkdir -p "${SRC_DIR}"
    if [ ! -f "${TARBALL_PATH}" ]; then
        log "downloading ${TARBALL}"
        URL="https://ftp.gnu.org/gnu/binutils/${TARBALL}"
        if command -v curl >/dev/null 2>&1; then
            curl -fL --retry 3 -o "${TARBALL_PATH}" "${URL}" \
                || die "download failed: ${URL}"
        else
            wget -O "${TARBALL_PATH}" "${URL}" || die "download failed: ${URL}"
        fi
    fi
    log "extracting ${TARBALL}"
    tar -xf "${TARBALL_PATH}" -C "${SRC_DIR}"
fi

# ---------------------------------------------------------------------- build
# --build 必须显式指定，否则 autotools 会因交叉三元组推断而失败。
# 注意：不要在 configure/make 之间用 `rm -rf` 清理，某些沙箱会把 rm 重定向到
# 回收站实现，导致 config.sub 之类的临时文件被移动走从而破坏构建。
mkdir -p "${BUILD_DIR}" "${PREFIX_DIR}"

cd "${BUILD_DIR}"
if [ ! -f Makefile ]; then
    log "configuring --target=mn10300-elf"
    "${SRCDIR}/configure" \
        --build="$(gcc -dumpmachine)" \
        --target=mn10300-elf \
        --prefix="${PREFIX_DIR}" \
        --disable-nls \
        --disable-werror \
        --disable-gdb \
        --disable-sim \
        --disable-gas \
        --disable-ld \
        --disable-gprof \
        --disable-gold \
        --disable-libctf \
        --with-system-zlib \
        --disable-shared
fi

log "building all-binutils (this takes a few minutes)"
make -j"$(nproc 2>/dev/null || echo 2)" all-binutils

OBJDUMP="${BUILD_DIR}/objdump"
[ -x "${OBJDUMP}" ] || die "objdump was not produced at ${OBJDUMP}"

# ------------------------------------------------------------------- install
log "installing to ${PREFIX_DIR}"
install -m 0755 "${OBJDUMP}" "${PREFIX_DIR}/objdump"

# --------------------------------------------------------------------- verify
log "verifying"
"${PREFIX_DIR}/objdump" --version | head -2
if ! "${PREFIX_DIR}/objdump" -i | grep -q 'mn10300'; then
    die "built objdump does not advertise the mn10300 target"
fi
"${PREFIX_DIR}/objdump" -i | grep -i 'mn10300' || true

cat <<EOF

[build] OK
  objdump : ${PREFIX_DIR}/objdump
  usage  : ${PREFIX_DIR}/objdump -b binary -m mn10300 -D -z --insn-width=16 \\
             --adjust-vma=0x402C0000 decoded/00_0100_402c0020.decoded.bin

  提示：MN103 必须显式 --insn-width=16，默认 32 位会整体错位。
EOF
