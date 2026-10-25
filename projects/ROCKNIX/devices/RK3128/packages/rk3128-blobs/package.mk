# SPDX-License-Identifier: GPL-2.0
PKG_NAME="rk3128-blobs"
PKG_VERSION="7d631e0d5b2d373b54d4533580d08fb9bd2eaad4"
PKG_SHA256="3fb6d03ea9a1a0cfae0e6ca35c4786e7d85a8420ace8b5177c475e30cf6fff72"
PKG_LICENSE="nonfree"
PKG_SITE="https://github.com/rockchip-linux/rkbin"
PKG_URL="${PKG_SITE}/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_TARGET="toolchain"
PKG_TOOLCHAIN="manual"

make_target() {
  for file in rk3128_ddr_300MHz_v2.12.bin rk3128x_miniloader_v2.57.bin rk3126_tee_ta_v2.01.bin; do
    test -s "bin/rk31/${file}" || exit 1
  done
}
