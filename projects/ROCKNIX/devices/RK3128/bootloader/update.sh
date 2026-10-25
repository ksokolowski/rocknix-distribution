#!/bin/sh
# SPDX-License-Identifier: GPL-2.0
set -eu
SYSTEM_ROOT=${SYSTEM_ROOT:-}
BOOT_ROOT=${BOOT_ROOT:-/flash}
source_dtb="${SYSTEM_ROOT}/usr/share/bootloader/device_trees/rk3128-powkiddy-a12-rev-a.dtb"
test -s "$source_dtb"
test -f "${BOOT_ROOT}/extlinux/extlinux.conf"
grep -q 'rk3128-powkiddy-a12-rev-a.dtb' "${BOOT_ROOT}/extlinux/extlinux.conf"
mount -o remount,rw "$BOOT_ROOT"
trap 'sync; mount -o remount,ro "$BOOT_ROOT"' EXIT
mkdir -p "${BOOT_ROOT}/device_trees"
cp "$source_dtb" "${BOOT_ROOT}/device_trees/rk3128-powkiddy-a12-rev-a.dtb.new"
mv "${BOOT_ROOT}/device_trees/rk3128-powkiddy-a12-rev-a.dtb.new" \
   "${BOOT_ROOT}/device_trees/rk3128-powkiddy-a12-rev-a.dtb"
echo UPDATE >/storage/.boot.hint
