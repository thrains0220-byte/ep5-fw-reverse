# MN103 交叉编译记录

工具均安装在项目 `toolchains/mn103/`，没有安装系统软件包。构建输入、完整 configure 参数与编译器哈希见 [构建清单](toolchain-build.json)。

## 输入

- GNU binutils 2.45，来源和 SHA-256 见 NOTICE.md。
- GCC 14.3.0：`https://gcc.gnu.org/pub/gcc/releases/gcc-14.3.0/`。
- GCC xz 包的 SHA-512：`cb4e3259640721bbd275c723fe4df53d12f9b1673afb3db274c22c6aa457865dccf2d6ea20b4fd4c591f6152e6d4b87516c402015900f06ce9d43af66d3b7a93`，与 GNU 发布目录的 `sha512.sum` 一致。
- 宿主数学库开发包通过 `apt-get download` 获取，用 `dpkg-deb --extract` 解压到 `toolchains/hostdeps/`；包版本及文件哈希保存在清单中。未执行系统安装。

## 构建

在不同的源码与构建目录中 configure，目标 `mn10300-elf`、语言仅 C、无目标系统头文件、关闭 bootstrap/multilib/LTO/线程与不需要的运行库。configure 指定本地 binutils、GMP/MPFR/MPC 头文件及库目录。

```bash
make -j4 all-gcc all-target-libgcc
make -j4 install-gcc install-target-libgcc
```

上述命令在 `toolchains/build-gcc/` 执行。完整配置可从 `toolchains/build-gcc/config.status --config` 读取；清单也保留了同一配置。日志在对应构建目录中。

## 验证

```bash
toolchains/mn103/bin/mn10300-elf-gcc --version
python3 tools/check_mn103_lut.py --out generated/ep5-lut-mn103.json
python3 -m unittest discover -s tests -v
```

色彩代码明确使用 `-mno-am33`，并要求两种反汇编模式得到相同指令，避免 CPU 模型接受了实机未必支持的扩展指令。测试链接脚本的地址完全是模型地址；固件加载器、原厂 ABI 桥接和真实内存映射需另行实现。

没有交叉编译器的环境会跳过目标 C 集成测试；只有 binutils 时仍可运行模型的汇编边界检查。本机本轮验收必须无跳过地运行目标案例，不能以跳过状态宣称通过。
