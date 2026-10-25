# SPDX-License-Identifier: GPL-2.0
PKG_NAME="a12-controls"
PKG_VERSION="1"
PKG_LICENSE="GPL-2.0-or-later"
PKG_DEPENDS_TARGET="toolchain xmlstarlet systemd freetype freetype:host"
# Init: a12-update-splash and the logo for the initramfs (no fbdev builds);
# host FreeType renders ES's font into its glyph table at build time.
PKG_DEPENDS_INIT="toolchain freetype:host"
PKG_TOOLCHAIN="manual"
# rocknix-splash sources render the KMS splash logo at build time (B12 step 3);
# ES's font is rendered into the initramfs glyph table (test 61).
PKG_DEPENDS_UNPACK="rocknix-splash emulationstation"
# Owner decision 2026-10-11 (test 44): no telemetry, no tty9 root shell,
# no NFS rpcbind, no mDNS (Samba is off). Masked in the read-only image.
# systemd-oomd (enabled upstream 2026-10, kills games.slice at 90 % swap):
# masked until measured on 256 MiB with zram (BACKLOG, decisions to revisit).
A12_MASKED_UNITS="rocknix-report-stats.timer rocknix-report-stats.service debug-shell.service rpcbind.service rpcbind.socket avahi-daemon.service avahi-daemon.socket systemd-oomd.service systemd-oomd.socket"

make_target() {
  ${CC} ${CFLAGS} ${LDFLAGS} -Wall -Wextra -o a12-controls a12-controls.c
  ${CC} ${CFLAGS} ${LDFLAGS} -Wall -Wextra -o a12-register-report a12-register-report.c
  # Status text from a TrueType font via FreeType, bitmap font as fallback.
  ${CC} ${CFLAGS} ${LDFLAGS} -Wall -Wextra -DSPLASH_TTF \
    -I${SYSROOT_PREFIX}/usr/include/freetype2 -o a12-splash \
    splash/splash-main.c splash/splash-fb.c splash/splash-draw.c \
    splash/splash-progress.c splash/splash-sd.c splash/splash-ttf.c splash/splash-kms.c \
    -lsystemd -lfreetype
  a12_gen_logo .
  # The first-boot resize runs from the system image (fs-resize.target,
  # no a12-splash.service, no fbcon): its meters need the tool here too.
  a12_build_update_splash .target
}

# The logo rocknix-splash draws, as a BMP for the KMS paths: its own main.c
# and renderer with the framebuffer and device checks wrapped. $1: output
# directory (target and init builds share PKG_BUILD and may run together).
a12_gen_logo() {
  local out="$1" rs="$(get_build_dir rocknix-splash)"
  mkdir -p "${out}"
  ${HOST_CC} -O2 -c -Dmain=rocknix_splash_main -I"${rs}" "${rs}/main.c" -o "${out}/rs-main.o"
  for src in fbsplash svg_parser svg_renderer; do
    ${HOST_CC} -O2 -c -I"${rs}" "${rs}/${src}.c" -o "${out}/rs-${src}.o"
  done
  ${HOST_CC} -O2 -Wall -Wextra -I"${rs}" -Isplash -o "${out}/gen-logo" splash/gen-logo.c splash/splash-draw.c \
    "${out}/rs-main.o" "${out}/rs-fbsplash.o" "${out}/rs-svg_parser.o" "${out}/rs-svg_renderer.o" \
    -Wl,--wrap=fb_init,--wrap=fb_flush,--wrap=fb_cleanup,--wrap=access,--wrap=get_display_rotation -lm
  "${out}/gen-logo" "${out}/logo.bmp"
}

# Status screen on KMS for the progress meters (B12 step 6), without
# systemd or FreeType at run time: the status line uses ES's font, rendered
# here into a glyph table (same pixels as a12-splash's FreeType text,
# splash-atlas-test). $1: output directory.
a12_build_update_splash() {
  local out="$1"
  mkdir -p "${out}"
  ${HOST_CC} -O2 -Wall -Wextra -Isplash -I${TOOLCHAIN}/include/freetype2 -o "${out}/gen-glyphs" \
    splash/gen-glyphs.c -L${TOOLCHAIN}/lib -Wl,-rpath,${TOOLCHAIN}/lib -lfreetype
  "${out}/gen-glyphs" "$(get_build_dir emulationstation)/resources/opensans_hebrew_condensed_regular.ttf" \
    "${out}/splash-glyphs.h"
  ${CC} ${CFLAGS} ${LDFLAGS} -Wall -Wextra -DSPLASH_ATLAS -Isplash -I"${out}" -o "${out}/a12-update-splash" \
    splash/update-splash.c splash/splash-draw.c splash/splash-atlas.c splash/splash-kms.c splash/splash-fb.c
}

make_init() {
  a12_build_update_splash .init
  a12_gen_logo .init
}

makeinstall_init() {
  mkdir -p "${INSTALL}/usr/bin" "${INSTALL}/usr/share/a12-splash"
  cp .init/a12-update-splash "${INSTALL}/usr/bin/"
  cp .init/logo.bmp "${INSTALL}/usr/share/a12-splash/logo.bmp"
}

makeinstall_target() {
  mkdir -p "${INSTALL}/usr/bin"
  cp a12-controls "${INSTALL}/usr/bin/"
  cp a12-register-report "${INSTALL}/usr/bin/"
  cp a12-splash "${INSTALL}/usr/bin/"
  cp .target/a12-update-splash "${INSTALL}/usr/bin/"
  cp "${PKG_BUILD}/a12-game-monitor" "${INSTALL}/usr/bin/"
  chmod 0755 "${INSTALL}/usr/bin/a12-game-monitor"
  cp "${PKG_BUILD}/a12-hardware-report" "${PKG_BUILD}/a12-sync-checks" "${PKG_BUILD}/a12-button-test" \
    "${INSTALL}/usr/bin/"
  chmod 0755 "${INSTALL}/usr/bin/a12-hardware-report" "${INSTALL}/usr/bin/a12-sync-checks" \
    "${INSTALL}/usr/bin/a12-button-test"
  cp "${PKG_BUILD}/a12-save-report" "${INSTALL}/usr/bin/"
  cp "${PKG_BUILD}/a12-exit-game" "${INSTALL}/usr/bin/"
  chmod 0755 "${INSTALL}/usr/bin/a12-exit-game"
  cp "${PKG_BUILD}/a12-usb-test" "${INSTALL}/usr/bin/"
  chmod 0755 "${INSTALL}/usr/bin/a12-usb-test"
  cp "${PKG_BUILD}/a12-neighbor-keepalive" "${INSTALL}/usr/bin/"
  chmod 0755 "${INSTALL}/usr/bin/a12-neighbor-keepalive"
  mkdir -p "${INSTALL}/etc"
  cp "${PKG_BUILD}/asound.conf" "${INSTALL}/etc/asound.conf"
  mkdir -p "${INSTALL}/etc/systemd/system"
  for unit in ${A12_MASKED_UNITS}; do
    ln -sf /dev/null "${INSTALL}/etc/systemd/system/${unit}"
  done
  cp "${PKG_BUILD}/rocknix-autostart.service" "${INSTALL}/etc/systemd/system/"
  # udev reads /etc/systemd/hwdb/hwdb.bin first; keep it on /storage.
  mkdir -p "${INSTALL}/etc/systemd"
  ln -sf /storage/.cache/hwdb ${INSTALL}/etc/systemd/hwdb
  cp "${PKG_BUILD}/a12-hwdb-update" "${INSTALL}/usr/bin/"
  chmod 0755 "${INSTALL}/usr/bin/a12-hwdb-update"
  # VLC's plugin cache on /storage (the vlc package links plugins.dat there).
  cp "${PKG_BUILD}/a12-vlc-cache" "${INSTALL}/usr/bin/"
  chmod 0755 "${INSTALL}/usr/bin/a12-vlc-cache"
  mkdir -p "${INSTALL}/usr/lib/sysctl.d"
  cp "${PKG_BUILD}/zz-a12-memory.conf" "${INSTALL}/usr/lib/sysctl.d/"
  mkdir -p "${INSTALL}/usr/lib/systemd/system"
  cp "${PKG_BUILD}/a12-diagnostics.service" "${PKG_BUILD}/a12-diagnostics.timer" \
    "${INSTALL}/usr/lib/systemd/system/"
  enable_service a12-diagnostics.timer
  cp "${PKG_BUILD}/a12-vlc-cache.service" "${INSTALL}/usr/lib/systemd/system/"
  # Device interrupts off CPU0 (USB host to CPU1, SD and DMA to CPU2).
  cp "${PKG_BUILD}/a12-irq-affinity" "${INSTALL}/usr/bin/"
  chmod 0755 "${INSTALL}/usr/bin/a12-irq-affinity"
  cp "${PKG_BUILD}/a12-irq-affinity.service" "${INSTALL}/usr/lib/systemd/system/"
  enable_service a12-irq-affinity.service
  enable_service a12-vlc-cache.service
  cp "${PKG_BUILD}/a12-usb-test.service" "${PKG_BUILD}/a12-usb-test.timer" \
    "${INSTALL}/usr/lib/systemd/system/"
  enable_service a12-usb-test.timer
  cp "${PKG_BUILD}/a12-neighbor-keepalive.service" "${PKG_BUILD}/a12-neighbor-keepalive.timer" \
    "${INSTALL}/usr/lib/systemd/system/"
  enable_service a12-neighbor-keepalive.timer
  # rocknix ships the idle zram recompression timer disabled; the A12 runs it
  # (skipped while a game runs, quirks drop-in). enable_service needs the
  # unit in this package, so link it directly.
  mkdir -p "${INSTALL}/usr/lib/systemd/system/timers.target.wants"
  ln -sf ../rocknix-memory-recompress.timer "${INSTALL}/usr/lib/systemd/system/timers.target.wants/"
  cp "${PKG_BUILD}/a12-splash.service" "${PKG_BUILD}/a12-splash-shutdown.service" \
    "${PKG_BUILD}/a12-splash-stopping.service" "${INSTALL}/usr/lib/systemd/system/"
  enable_service a12-splash.service
  enable_service a12-splash-shutdown.service
  enable_service a12-splash-stopping.service
  mkdir -p "${INSTALL}/usr/share/a12-splash"
  cp "${PKG_BUILD}/logo.bmp" "${INSTALL}/usr/share/a12-splash/logo.bmp"
  mkdir -p "${INSTALL}/usr/lib/systemd/system-shutdown"
  cp "${PKG_BUILD}/a12-splash.shutdown-hook" "${INSTALL}/usr/lib/systemd/system-shutdown/a12-splash"
  chmod 0755 "${INSTALL}/usr/lib/systemd/system-shutdown/a12-splash"
  # Upstream's system.slice floor (MemoryLow=192M, MemoryMin=64M, for oomd,
  # which the A12 masks) leaves only the game to reclaim on 225 MB: the
  # running game's memory went to zram and Metal Slug stalled (test 55).
  mkdir -p "${INSTALL}/usr/lib/systemd/system/system.slice.d"
  cp "${PKG_BUILD}/20-a12-system-slice.conf" \
    "${INSTALL}/usr/lib/systemd/system/system.slice.d/20-a12-system-slice.conf"
  mkdir -p "${INSTALL}/usr/lib/systemd/system.conf.d"
  cp "${PKG_BUILD}/10-a12-watchdog.conf" "${INSTALL}/usr/lib/systemd/system.conf.d/"
  mkdir -p "${INSTALL}/usr/share/commander" "${INSTALL}/usr/share/a12-controls"
  cp "${PKG_BUILD}/commander.cfg" "${INSTALL}/usr/share/commander/commander.cfg"
  cp "${PKG_BUILD}/Start Retroarch.sh" "${INSTALL}/usr/share/a12-controls/"
  mkdir -p "${INSTALL}/usr/lib/autostart/common"
  cp "${PKG_BUILD}/021-a12-tools" "${INSTALL}/usr/lib/autostart/common/"
  chmod 0755 "${INSTALL}/usr/lib/autostart/common/021-a12-tools"
  # Writes to /storage/roms: device stage, after automount (autostart-automount-test.py).
  mkdir -p "${INSTALL}/usr/lib/autostart/RK3128"
  cp "${PKG_BUILD}/022-a12-bios" "${INSTALL}/usr/lib/autostart/RK3128/"
  chmod 0755 "${INSTALL}/usr/lib/autostart/RK3128/022-a12-bios"
}
