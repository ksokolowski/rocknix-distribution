#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""A12 splash units, ES drop-in and shutdown hook (boot splash plan, Task 5).

The splash labels jobs by the unit's Description (owner, 2026-10-17: keep
the screen device-neutral), so every A12 unit has one and none says "A12".
"""
import pathlib

root = pathlib.Path(__file__).resolve().parents[5]
dev = root / "projects/ROCKNIX/devices/RK3128"
src = dev / "packages/a12-controls/sources"
boot = (src / "a12-splash.service").read_text()
down = (src / "a12-splash-shutdown.service").read_text()
hook = (src / "a12-splash.shutdown-hook").read_text()
stopping = (src / "a12-splash-stopping.service").read_text()
es = (dev / "packages/quirks/system.d/emustation.service.d/30-a12-splash.conf").read_text()
mk = (dev / "packages/a12-controls/package.mk").read_text()

assert "DefaultDependencies=no" in boot and "Type=simple" in boot
# Runs with fbdev or KMS (triggering conditions: either one is enough).
assert "ConditionPathExists=|/dev/fb0\n" in boot and "ConditionPathExists=|/dev/dri/card0\n" in boot
assert "ConditionPathExists=/dev/fb0" not in boot
assert "ExecStart=/usr/bin/a12-splash\n" in boot and "WantedBy=sysinit.target" in boot
assert "Requires=" not in boot
# Stopped by the shutdown transaction, so it can never draw over the shutdown screen.
assert "Conflicts=shutdown.target" in boot and "Before=shutdown.target" in boot
assert "After=emustation.service" in down and "ExecStop=/usr/bin/a12-splash --shutdown" in down
assert "Type=oneshot" in down and "RemainAfterExit=yes" in down
assert 'splash=${A12_SPLASH:-/usr/bin/a12-splash}' in hook and 'exec "$splash" --final' in hook
assert '[ "$1" = poweroff ] || exit 0' in hook  # behaviour: poweroff-blank-test
# Shutdown progress: started by the shutdown transaction, never stopped by it.
assert "DefaultDependencies=no" in stopping and "WantedBy=shutdown.target" in stopping
assert "ExecStart=/usr/bin/a12-splash --stopping" in stopping and "Type=simple" in stopping
assert "Conflicts=" not in stopping and "After=a12-splash-shutdown.service" in stopping
assert "enable_service a12-splash-stopping.service" in mk and '"${PKG_BUILD}/a12-splash-stopping.service"' in mk
# TTF status text is built in; the bitmap font stays as the fallback.
# KMS backend (B12 step 1) is built in; fbdev stays the default.
assert "splash/splash-kms.c" in mk
main = (src / "splash/splash-main.c").read_text()
assert 'getenv("A12_SPLASH_FORCE_KMS")' in main and 'open("/dev/fb0", O_RDWR)' in main
assert "-DSPLASH_TTF" in mk and "splash/splash-ttf.c" in mk and "-lfreetype" in mk
assert "freetype" in mk.split('PKG_DEPENDS_TARGET="', 1)[1].split('"', 1)[0].split()
assert "ExecStart=\n" in es
assert "--splash-image /storage/.cache/a12-splash/logo.bmp" in es and "--no-splash" not in es
# ES draws its own themed splash bar; no progress hand-over variable or patch.
assert "ES_SPLASH_PROGRESS_START" not in es
for es_patch in (dev / "patches/emulationstation").glob("*.patch"):
    assert "splash" not in es_patch.read_text(encoding="latin-1").lower(), es_patch.name
for needle in ("enable_service a12-splash.service", "enable_service a12-splash-shutdown.service",
               "/usr/lib/systemd/system-shutdown/a12-splash"):
    assert needle in mk, needle
auto = (src / "rocknix-autostart.service").read_text()
after = " ".join(l.split("=", 1)[1] for l in auto.splitlines() if l.startswith("After="))
# graphical.target waits for multi-user.target -> sshd -> network.target.
assert "network.target" not in after and "graphical.target" not in after, \
    "ES must not wait for the network (owner decision)"
assert "userconfig.service" in after and "Before=emustation.service" in auto
assert 'cp "${PKG_BUILD}/rocknix-autostart.service" "${INSTALL}/etc/systemd/system/"' in mk

# Descriptions are what the boot and shutdown screens show.
for unit in sorted(src.glob("*.service")) + sorted(src.glob("*.timer")):
    desc = [l[12:] for l in unit.read_text().splitlines() if l.startswith("Description=")]
    assert len(desc) == 1 and desc[0].strip(), f"{unit.name}: no Description"
    assert "a12" not in desc[0].lower(), f"{unit.name}: Description names the A12: {desc[0]}"
print("splash units: ok")
