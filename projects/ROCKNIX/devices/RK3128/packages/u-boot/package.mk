# SPDX-License-Identifier: GPL-2.0
PKG_NAME="u-boot"
PKG_VERSION="ece349ade2973e220f524ce59e59711cc919263f"
PKG_SHA256="c51a3c160ee8a7f4304e52498ecfe327789c9464a3681b5c5bd3c72b1f18a079"
PKG_LICENSE="GPL-2.0"
PKG_SITE="https://github.com/u-boot/u-boot"
PKG_URL="${PKG_SITE}/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain rk3128-blobs Python3:host swig:host pyelftools:host"
PKG_TOOLCHAIN="manual"

make_target() {
  local rkbin="$(get_build_dir rk3128-blobs)"
  local blobs="${rkbin}/bin/rk31"
  # A12_UBOOT_DISPLAY=yes builds the unverified panel/logo draft (B3).
  local defconfig="powkiddy-a12-rk3128_defconfig"
  [ "${A12_UBOOT_DISPLAY}" = "yes" ] && defconfig="powkiddy-a12-display-rk3128_defconfig"
  setup_pkg_config_host
  ARCH=arm CROSS_COMPILE="${TARGET_PREFIX}" LDFLAGS="" make HOSTCC="${HOST_CC}" HOSTCFLAGS="-O2 -I${TOOLCHAIN}/include" HOSTLDFLAGS="${HOST_LDFLAGS}" "${defconfig}"
  ARCH=arm CROSS_COMPILE="${TARGET_PREFIX}" LDFLAGS="" \
    _python_sysroot="${TOOLCHAIN}" _python_prefix=/ _python_exec_prefix=/ \
    make HOSTCC="${HOST_CC}" HOSTCFLAGS="-O2 -I${TOOLCHAIN}/include" HOSTLDFLAGS="${HOST_LDFLAGS}" u-boot-dtb.bin
  tools/mkimage -n rk3128 -T rksd -d "${blobs}/rk3128_ddr_300MHz_v2.12.bin" idbloader.img
  cat "${blobs}/rk3128x_miniloader_v2.57.bin" >>idbloader.img
  "${rkbin}/tools/loaderimage" --pack --uboot u-boot-dtb.bin uboot.img 0x60000000 --size 1024 4
  "${rkbin}/tools/loaderimage" --pack --trustos "${blobs}/rk3126_tee_ta_v2.01.bin" trust.img --size 1024 4
}

makeinstall_target() {
  mkdir -p "${INSTALL}/usr/share/bootloader"
  cp idbloader.img uboot.img trust.img "${INSTALL}/usr/share/bootloader/"
  cp "${PROJECT_DIR}/${PROJECT}/devices/${DEVICE}/bootloader/update.sh" "${INSTALL}/usr/share/bootloader/"
}
