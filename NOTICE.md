# Sources and attribution

This project does not depend on thrains0220-byte/ep5-fw-reverse.

- **Official input:** OM Digital Solutions firmware catalog, model E-P5 / 1080, build 1800. Firmware copyright remains with its owners. Downloaded and decoded images are local ignored inputs, not original project source.
- **fishcu/oly_fw_analysis:** https://github.com/fishcu/oly_fw_analysis at `a61498eecba1125010956864acbefaa1e4ff5f9e`. The existing catalog client and container tools were executed unchanged. Its SD debug research supplied a cross-model hypothesis, independently tested against E-P5 instructions. Respect its Apache-2.0 and documented third-party exceptions.
- **cmdada/em10-fw:** https://github.com/cmdada/em10-fw at `6adb3bef36239859ae3fcd94b0dbb7db6de6ffa1`. Its unchanged base-finder and GPL-3.0 GNU-derived CPU/gen/ISA sources are used locally. `tools/ep5_gate_probe.c` is GPL-3.0-or-later and is linked with that CPU. Preserve the upstream source, notices and GPL obligations when redistributing the combined probe; do not distribute a binary without corresponding source.
- **cakelesscoder/caduceus-ep7:** https://github.com/cakelesscoder/caduceus-ep7 at `78dbbc433ba0d04f1c31376937a98abede881526`. Read as architectural reference. No E-P7 firmware, hooks or look tables were copied into the E-P5 implementation.
- **GNU binutils 2.45:** https://ftp.gnu.org/gnu/binutils/binutils-2.45.tar.xz, SHA-256 `c50c0e7f9cb188980e2cc97e4537626b1672441815587f1eab69d2a1bfbef5d2`. Locally built for MN103 disassembly; source and binaries remain ignored build dependencies.
- **GNU GCC 14.3.0:** https://gcc.gnu.org/pub/gcc/releases/gcc-14.3.0/. Built locally for freestanding MN103 C; verified archive/build inputs are recorded in `docs/toolchain-build.json`. Preserve GCC and runtime-library notices and the corresponding licenses if redistributing toolchain or linked test binaries.
- **Latent Studios:** https://latentstudios.art/firmware/guide/ supplied product/workflow inspiration. Its firmware and film assets were not downloaded or incorporated.

Original RGB LUT kernel, LUT compiler and inspection code were written for this project. Experimental Warm Negative is an original uncalibrated colour recipe, not a claim of measured film-stock reproduction.
