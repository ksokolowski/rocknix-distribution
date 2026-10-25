# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2024-present ROCKNIX (https://github.com/ROCKNIX)

PKG_NAME="portmaster"
PKG_VERSION="2026.06.23-0015"
PKG_SHA256="772f2d56fc1abfbf79a3404ca78f240776c81c5a5b92786a0a748ae554339b7b"
PKG_LICENSE="MIT"
PKG_SITE="https://github.com/PortsMaster/PortMaster-GUI"
PKG_URL="${PKG_SITE}/releases/download/${PKG_VERSION}/PortMaster.zip"
PKG_DEPENDS_TARGET="toolchain rocknix-hotkey gamecontrollerdb oga_controls control-gen xmlstarlet list-guid gst-plugins-base zip"
# gst-plugins-base does not build for 32-bit ARM (Thumb-2 inline assembly
# in ARM mode); PortMaster ran on the Powkiddy A12 without it.
[ "${ARCH}" = "arm" ] && PKG_DEPENDS_TARGET="${PKG_DEPENDS_TARGET/ gst-plugins-base/}"
PKG_LONGDESC="Portmaster - a simple tool that allows you to download various game ports"
PKG_TOOLCHAIN="manual"

COMPAT_URL="https://github.com/ROCKNIX/packages/raw/main/compat.tar.gz" #f0f5e94

makeinstall_target() {
  export STRIP=true

  mkdir -p ${INSTALL}/usr/config/PortMaster
    cp -a ${PKG_DIR}/sources/* ${INSTALL}/usr/config/PortMaster

  mkdir -p ${INSTALL}/usr/bin
    cp -a ${PKG_DIR}/scripts/* ${INSTALL}/usr/bin

  mkdir -p ${INSTALL}/usr/config/PortMaster/release
    curl -Lo ${INSTALL}/usr/config/PortMaster/release/PortMaster.zip ${PKG_URL}

  # The compat libraries are aarch64 builds.
  if [ "${ARCH}" = "aarch64" ]; then
    mkdir -p ${INSTALL}/usr/lib/compat
      curl -Lo ${PKG_BUILD}/compat.tar.gz ${COMPAT_URL}
      tar -xvf ${PKG_BUILD}/compat.tar.gz -C ${INSTALL}/usr/lib
      rm -rf ${INSTALL}/usr/lib/compat/libSDL2-2.0.so.0*
  fi
}
