# SPDX-License-Identifier: GPL-2.0
PKG_NAME="rk3128-hardware"
PKG_VERSION="1"
PKG_LICENSE="GPL-2.0-or-later"
PKG_DEPENDS_TARGET="toolchain linux"
PKG_TOOLCHAIN="manual"
PKG_IS_KERNEL_PKG="yes"

make_target() {
  kernel_make -C "$(kernel_path)" M="${PKG_BUILD}" modules
}

makeinstall_target() {
  mkdir -p "${INSTALL}/$(get_full_module_dir)/${PKG_NAME}"
  cp *.ko "${INSTALL}/$(get_full_module_dir)/${PKG_NAME}/"
}
