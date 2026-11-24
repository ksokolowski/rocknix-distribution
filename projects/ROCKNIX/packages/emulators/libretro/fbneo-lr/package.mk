# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2024-present ROCKNIX (https://github.com/ROCKNIX)

PKG_NAME="fbneo-lr"
PKG_VERSION="e5d22930f772b8baff514ec57e5786ea50c1c72e"
PKG_SHA256="0cb4116f31b3320dda5d6ade26ab2f9043b4c8266856dc15912ec2b0d39314e6"
PKG_LICENSE="Non-commercial"
PKG_SITE="https://github.com/libretro/FBNeo"
PKG_URL="${PKG_SITE}/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain retroarch"
PKG_LONGDESC="Port of Final Burn Neo to Libretro (v0.2.97.38)."
PKG_TOOLCHAIN="make"

PKG_MAKE_OPTS_TARGET=" -C ../src/burner/libretro USE_CYCLONE=0 profile=performance"

# KNULLI uses the ARM assembly 68000 core on its RK3128 target.
if [ "${DEVICE}" = "RK3128" ]; then
  PKG_MAKE_OPTS_TARGET=" -C ../src/burner/libretro USE_CYCLONE=1 profile=performance"
fi

if [[ "${TARGET_FPU}" =~ "neon" ]]; then
  PKG_MAKE_OPTS_TARGET+=" HAVE_NEON=1"
fi

pre_make_target() {
  # Assembly without .note.GNU-stack; glibc will not dlopen an RWE core into RetroArch.
  if [ "${TARGET_ARCH}" = "arm" ]; then
    export LDFLAGS+=" -Wl,-z,noexecstack"
  fi
}

post_unpack() {
  sed -i "s|LDFLAGS += -static-libgcc -static-libstdc++|LDFLAGS += -static-libgcc|" ${PKG_BUILD}/src/burner/libretro/Makefile
}

makeinstall_target() {
  mkdir -p ${INSTALL}/usr/lib/libretro
    cp -a ${PKG_BUILD}/src/burner/libretro/fbneo_libretro.so ${INSTALL}/usr/lib/libretro
}
