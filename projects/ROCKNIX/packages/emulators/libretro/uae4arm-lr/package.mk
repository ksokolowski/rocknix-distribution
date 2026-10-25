# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2024-present ROCKNIX (https://github.com/ROCKNIX)

PKG_NAME="uae4arm-lr"
PKG_VERSION="276979efa4f862d1f84afeff5a2e794de4744024"
PKG_SHA256="97a793a6624055cb99c83ca0202b0acd9403bab8c9e16f3dff85d0fdccb944ff"
PKG_LICENSE="GPL-2.0-or-later"
PKG_SITE="https://github.com/Chips-fr/uae4arm-rpi"
PKG_URL="${PKG_SITE}/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain retroarch flac libogg mpg123"
PKG_LONGDESC="Port of uae4arm for libretro (rpi/android)"

PKG_MAKE_OPTS_TARGET="-f Makefile.libretro platform=unix_aarch64"
# The A12 is 32-bit ARMv7 (Cortex-A7, NEON-VFPv4): unix_aarch64 assembly does
# not build there, the core has a matching target.
if [ "${DEVICE}" = "RK3128" ]; then
  PKG_MAKE_OPTS_TARGET="-f Makefile.libretro platform=classic_armv7_a7"
fi

post_unpack() {
  # classic_armv7_a7 does not link the libraries the core uses (A12).
  if [ "${DEVICE}" = "RK3128" ]; then
    sed -i '/platform), classic_armv7_a7)/a\\tLDFLAGS += -lz -lpthread -lFLAC -lmpg123 -ldl' ${PKG_BUILD}/Makefile.libretro
  fi
  sed -i 's/-lFLAC/-lFLAC -logg/' ${PKG_BUILD}/Makefile.libretro
}

makeinstall_target() {
  mkdir -p ${INSTALL}/usr/lib/libretro
    cp -a uae4arm_libretro.so ${INSTALL}/usr/lib/libretro
}
