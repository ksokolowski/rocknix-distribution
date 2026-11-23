# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2024-present ROCKNIX (https://github.com/ROCKNIX)

PKG_NAME="vice-lr"
PKG_VERSION="5ebe7d333ab15be57a9dde5f46c29a5bbd5f44f8"
PKG_SHA256="45ed7b653473e0a819fdca3679e3797c4606edb8d115afa5fd26265044431225"
PKG_LICENSE="GPL-2.0-or-later"
PKG_SITE="https://github.com/libretro/vice-libretro"
PKG_URL="${PKG_SITE}/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain retroarch"
PKG_LONGDESC="Versatile Commodore 8-bit Emulator version 3.0"

make_target() {
  if [ ! -d "built" ]; then
    mkdir built
  fi

  local EMUTYPES="x128 x64sc x64dtv xscpu64 xplus4 xvic xcbm5x0 xcbm2 xpet x64"
  # The A12 ships the C64 only: cycle-exact x64sc and the fast x64.
  if [ "${DEVICE}" = "RK3128" ]; then
    EMUTYPES="x64sc x64"
  fi
  for EMUTYPE in ${EMUTYPES}; do
    make clean
    make platform=unix EMUTYPE=${EMUTYPE}
    mv vice_*_libretro.so built
  done
}

makeinstall_target() {
  mkdir -p ${INSTALL}/usr/lib/libretro
  if [ "${DEVICE}" = "RK3128" ]; then
    cp -a built/vice_x64sc_libretro.so built/vice_x64_libretro.so ${INSTALL}/usr/lib/libretro
    return
  fi
    cp -a built/vice_x128_libretro.so ${INSTALL}/usr/lib/libretro
    cp -a built/vice_x64_libretro.so ${INSTALL}/usr/lib/libretro
    cp -a built/vice_xplus4_libretro.so ${INSTALL}/usr/lib/libretro
    cp -a built/vice_xvic_libretro.so ${INSTALL}/usr/lib/libretro
    cp -a built/vice_xpet_libretro.so ${INSTALL}/usr/lib/libretro
}
