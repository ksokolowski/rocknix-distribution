# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2021-present Xargon (https://github.com/XargonWan)
# Copyright (C) 2023 JELOS (https://github.com/JustEnoughLinuxOS)
# Copyright (C) 2025 ROCKNIX Team (https://github.com/ROCKNIX)

PKG_NAME="rclone"
PKG_VERSION="1.71.0"
PKG_DEPENDS_TARGET="toolchain fuse rsync"
PKG_LONGDESC="rsync for cloud storage"
PKG_TOOLCHAIN="manual"

case ${ARCH} in
    arm)
      RCLONE_ARCH="arm-v7"
      PKG_SHA256="d645c44ec7c485e6d518a0575f2dd4c2b75fd70e547ed367b39bbf9e823c81e4"
      PKG_SOURCE_NAME="rclone-${PKG_VERSION}-arm-v7.zip"
    ;;
    aarch64)
      RCLONE_ARCH="arm64"
      PKG_SHA256="b710ac2ded37261d2cc6ab046dcd644828944524cf1ee7c2b17dd746f0fd8684"
    ;;
    *)
      RCLONE_ARCH="amd64"
    ;;
esac

PKG_URL="https://downloads.rclone.org/v${PKG_VERSION}/rclone-v${PKG_VERSION}-linux-${RCLONE_ARCH}.zip"
PKG_RCLONE="rclone-v${PKG_VERSION}-linux-${RCLONE_ARCH}/rclone"

unpack() {
  mkdir -p ${PKG_BUILD}
  unzip "${SOURCES}/rclone/${PKG_SOURCE_NAME}" -d "${PKG_BUILD}/"
}

makeinstall_target() {
  mkdir -p ${INSTALL}/usr/bin/
  mkdir -p ${INSTALL}/usr/config/
  cp cloud_backup ${INSTALL}/usr/bin/
  cp cloud_restore ${INSTALL}/usr/bin/
  cp cloud_sync_helper ${INSTALL}/usr/bin/
  cp cloud_sync_cleanup_duplicates.sh ${INSTALL}/usr/bin/
  cp ${PKG_BUILD}/${PKG_RCLONE} ${INSTALL}/usr/bin/
  chmod 0755 ${INSTALL}/usr/bin/*
  cp cloud_sync-rules.txt ${INSTALL}/usr/config/
  cp cloud_sync.conf ${INSTALL}/usr/config/
  cp cloud_sync.conf.defaults ${INSTALL}/usr/config/
  cp cloud_sync-rules.txt.defaults ${INSTALL}/usr/config/
  chmod 755 ${INSTALL}/usr/bin/rclone
  mkdir -p ${INSTALL}/usr/config/modules
  ln -sf /usr/bin/cloud_backup ${INSTALL}/usr/config/modules/cloud_backup.sh
  ln -sf /usr/bin/cloud_restore ${INSTALL}/usr/config/modules/cloud_restore.sh
}
