# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2024-present ROCKNIX (https://github.com/ROCKNIX)

PKG_NAME="scummvm-sa"
PKG_VERSION="2026.1.0"
PKG_SHA256="fe67167459f68f2335babc86e63fcb1a2e62bce8fac6b435e28240a07e2d7b59"
PKG_LICENSE="GPL-3.0-or-later"
PKG_SITE="https://github.com/scummvm/scummvm"
PKG_URL="${PKG_SITE}/archive/refs/tags/v${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain SDL2 SDL2_net freetype fluidsynth soundfont-generaluser libvorbis libogg libjpeg-turbo libpng libvpx zlib libmpeg2 curl"
PKG_LONGDESC="Script Creation Utility for Maniac Mansion Virtual Machine"
PKG_BUILD_FLAGS="-cfg-libs"

PKG_CONFIGURE_OPTS_TARGET="--host=${TARGET_NAME} \
                           --backend=sdl \
                           --disable-alsa \
                           --with-sdl-prefix=${SYSROOT_PREFIX}/usr/bin \
                           --disable-debug \
                           --enable-release \
                           --enable-vkeybd \
                           --enable-optimizations"

if [ "${PIPEWIRE_SUPPORT}" = "yes" ]; then
  PKG_DEPENDS_TARGET+=" pipewire"
fi

# configure leaves the NEON blitters off on 32-bit ARM.
if [ "${TARGET_ARCH}" = "arm" ] && [[ "${TARGET_FPU}" =~ "neon" ]]; then
  PKG_CONFIGURE_OPTS_TARGET+=" --enable-ext-neon"
fi

case ${DEVICE} in
  SM8550|SM8650)
    PKG_CONFIGURE_OPTS_TARGET+=" --disable-opengl-game --disable-opengl-game-classic --disable-opengl-game-shaders --opengl-mode=none"
    ;;
  *)
    PKG_CONFIGURE_OPTS_TARGET+=" --opengl-mode=auto"
    ;;
esac

post_unpack() {
  sed -i "s|sdl-config|sdl2-config|g" ${PKG_BUILD}/configure
}

post_makeinstall_target() {
  mkdir -p ${INSTALL}/usr/config/scummvm
    cp -a ${PKG_DIR}/config/* ${INSTALL}/usr/config/scummvm

  # A12: GPU scaling; auto music: Roland MT-32 for MT-32 games when the owner's ROMs are in the
  # BIOS folder (022-a12-bios sets mt32_device), FluidSynth for General MIDI games, else AdLib.
  if [ "${DEVICE}" = "RK3128" ]; then
    sed -i -e 's/^music_driver=.*/music_driver=auto/' -e 's/^gfx_mode=.*/gfx_mode=opengl/' \
      -e '/^\[scummvm\]/a extrapath=/storage/roms/bios' ${INSTALL}/usr/config/scummvm/scummvm.ini
  fi

  mkdir -p ${INSTALL}/usr/config/scummvm/themes
    cp -a ${PKG_BUILD}/gui/themes ${INSTALL}/usr/config/scummvm/themes

  mkdir -p ${INSTALL}/usr/bin
    cp -a ${PKG_DIR}/scripts/start_scummvm.sh ${INSTALL}/usr/bin

  rm -rf ${INSTALL}/usr/share/{appdata,applications,doc,icons,man}
}
