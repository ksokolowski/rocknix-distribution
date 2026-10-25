#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
toolchain=${TOOLCHAIN:-$(cd "$here/../../../../../.." && pwd)/build.ROCKNIX-RK3128.arm/toolchain}
cc="$toolchain/bin/armv7ve-rocknix-linux-gnueabi-gcc-16.2.0"
flags="-O2 -march=armv7ve -mtune=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard"
out=${1:-$here/out}
mkdir -p "$out"
# ROCKNIX glibc targets kernel >= 6.18 and may assume time64 syscalls that
# KNULLI's 4.4 kernel lacks. Build the probe once with PROBE_CC (the KNULLI
# toolchain) so the same static binary runs on both systems.
: "${PROBE_CC:?set PROBE_CC to the KNULLI rk3128 toolchain gcc (static probe for kernel 4.4)}"
"$PROBE_CC" $flags -static -o "$out/a12-perfprobe" "$here/a12-perfprobe.c"
for tool in a12-vop-dclk a12-testpattern; do
  "$PROBE_CC" $flags -static -o "$out/$tool" "$here/$tool.c"
done
if [ -x "$cc" ]; then
  # dlopen()s the core, so it is dynamic; ship it with the runtime bundle used in test 13.
  # RetroArch runs with an executable stack; cores with Cyclone ARM assembly need it.
  "$cc" $flags -Wl,-z,execstack -I"$here" -o "$out/core-benchmark" "$here/core-benchmark.c" -ldl -Wl,--no-as-needed -lm -Wl,--as-needed
  sysroot=$("$cc" -print-sysroot)
  "$cc" $flags -Wall -Wextra -Werror -I"$sysroot/usr/include/libdrm" \
    -o "$out/a12-present-probe" "$here/a12-present-probe.c" -ldrm -lm
fi
cp "$here/a12-bench" "$out/"
file "$out/a12-perfprobe" | grep -q "statically linked"
