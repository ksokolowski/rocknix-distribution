# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2024-present ROCKNIX (https://github.com/ROCKNIX)

. ${ROOT}/packages/sysutils/squashfs-tools/package.mk

PKG_DEPENDS_TARGET="toolchain libarchive lzo lz4 zstd"
# Host mksquashfs needs LZ4 for SQUASHFS_COMPRESSION="lz4" (RK3128/A12).
PKG_DEPENDS_HOST="ccache:host zlib:host lzo:host lz4:host zstd:host"
PKG_NEED_UNPACK="$(get_pkg_directory zlib) $(get_pkg_directory lzo) $(get_pkg_directory lz4) $(get_pkg_directory zstd)"

make_target() {
  make -C squashfs-tools clean
  make -C squashfs-tools \
          unsquashfs
}

make_host() {
  make -C squashfs-tools \
          mksquashfs \
          XZ_SUPPORT=0 \
          LZO_SUPPORT=1 \
          LZ4_SUPPORT=1 \
          ZSTD_SUPPORT=1 \
          XATTR_SUPPORT=0 \
          XATTR_DEFAULT=0 \
          INCLUDEDIR="-I. -I${TOOLCHAIN}/include"
}

makeinstall_target() {
  mkdir -p ${INSTALL}/usr/bin
  cp ${PKG_BUILD}/squashfs-tools/unsquashfs ${INSTALL}/usr/bin/unsquashfs
  chmod 755 ${INSTALL}/usr/bin/unsquashfs
}
