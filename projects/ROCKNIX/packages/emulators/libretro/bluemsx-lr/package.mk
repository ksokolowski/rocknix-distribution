# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2024-present ROCKNIX (https://github.com/ROCKNIX)

PKG_NAME="bluemsx-lr"
PKG_VERSION="e3086eb5d36d77fa11704cf53dc176686e70127d"
PKG_SHA256="55d7f4feed17592d2c726469b00ec239cb4b8f2093a29b912931f25035838b9b"
PKG_LICENSE="GPL-2.0-or-later"
PKG_SITE="https://github.com/libretro/blueMSX-libretro"
PKG_URL="${PKG_SITE}/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain retroarch"
PKG_LONGDESC="Port of blueMSX to the libretro API."

PKG_MAKE_OPTS_TARGET="-f Makefile.libretro"

makeinstall_target() {
  mkdir -p ${INSTALL}/usr/lib/libretro
    cp -a bluemsx_libretro.so ${INSTALL}/usr/lib/libretro
  # The A12 carries the machine configs, databases and free C-BIOS ROMs, not
  # the proprietary BIOS dumps (the core falls back to C-BIOS for cartridges);
  # a12-controls seeds them into the BIOS directory.
  if [ "${DEVICE}" = "RK3128" ]; then
    mkdir -p ${INSTALL}/usr/share/bluemsx
    cp -a system/bluemsx/Machines system/bluemsx/Databases ${INSTALL}/usr/share/bluemsx
    find ${INSTALL}/usr/share/bluemsx/Machines -type f -iname '*.rom' ! -name 'cbios_*' -delete
  fi
}
