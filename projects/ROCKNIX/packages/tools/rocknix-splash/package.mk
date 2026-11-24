# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2025 ROCKNIX (https://github.com/ROCKNIX)

PKG_NAME="rocknix-splash"
PKG_VERSION="9d295bcb74be2282e32c6b614efbea6036974ba8"
PKG_SHA256="ffa718a9bbcbf69857b91acf854abaf4cc00a7802f61d531341517546c26e635"
# The A12 keeps 81b104a (adaptive scaling, verified boot logo); 9d295bc adds
# an obfuscated official-build check (RK3128 upstream/TRACKER.md D17).
case ${DEVICE} in
  RK3128)
    PKG_VERSION="81b104a83c11bd3ecf5a4ce3ef1d4ed3fc5193b3"
    PKG_SHA256="31f61f2ffd7faf3baf7a881ccda2748e1c3713e20967a73aa7b85d4fc4cbd2a4"
  ;;
esac
PKG_LICENSE="GPL"
PKG_SITE="https://rocknix.org"
PKG_URL="https://github.com/ROCKNIX/${PKG_NAME}/archive/${PKG_VERSION}.tar.gz"
PKG_DEPENDS_INIT="toolchain"
PKG_LONGDESC="ROCKNIX splash screen application"

pre_make_init() {
  export LDFLAGS="${LDFLAGS} -lm"
}
