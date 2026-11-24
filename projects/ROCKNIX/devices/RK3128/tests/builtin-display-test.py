#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Panel and TTL PHY are built into the kernel so the initramfs splash can draw.

As modules they loaded from SYSTEM via udev at ~18.4 s (test 19 journal), so
/dev/fb0 did not exist while the initramfs ran rocknix-splash.
"""
import pathlib
import re

device = pathlib.Path(__file__).resolve().parents[1]
config = (device / "linux/linux.arm.conf").read_text()
for option in ("CONFIG_DRM_PANEL_POWKIDDY_A12=y", "CONFIG_PHY_ROCKCHIP_A12_TTL=y"):
    assert option + "\n" in config, option

makefile = (device / "packages/rk3128-hardware/sources/Makefile").read_text()
assert "panel-a12.o" not in makefile and "a12-ttl-phy.o" not in makefile, "still built as modules"
for gone in ("panel-a12.c", "a12-ttl-phy.c"):
    assert not (device / "packages/rk3128-hardware/sources" / gone).exists(), f"{gone} duplicated"

patch = (device / "patches/linux/0010-a12-panel-and-ttl-phy-builtin.patch").read_text()
# Object names keep KBUILD_MODNAME panel_a12 / a12_ttl_phy (refresh_60hz parameter path).
assert re.search(r"^\+obj-\$\(CONFIG_DRM_PANEL_POWKIDDY_A12\)\s*\+= panel-a12\.o$", patch, re.M)
assert re.search(r"^\+obj-\$\(CONFIG_PHY_ROCKCHIP_A12_TTL\)\s*\+= a12-ttl-phy\.o$", patch, re.M)
assert "module_param(refresh_60hz" in patch
assert "MODULE_DEVICE_TABLE(of, a12_panel_match)" in patch
assert re.search(r"^\+config DRM_PANEL_POWKIDDY_A12$", patch, re.M)
assert re.search(r"^\+config PHY_ROCKCHIP_A12_TTL$", patch, re.M)

report = (device / "packages/a12-controls/sources/a12-hardware-report").read_text()
assert "/sys/bus/platform/drivers/" in report, "built-in drivers would be reported absent"
# console=tty0 made systemd's console reset clear the splash (owner, 2026-10-09);
# like KNULLI, keep only the serial console so the logo stays until ES.
options = (device / "options").read_text()
assert "console=tty0" not in options, "screen console would blank the splash"
assert "console=ttyS0,115200" in options
print("builtin display: ok")
