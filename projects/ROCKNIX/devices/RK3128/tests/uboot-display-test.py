#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""B3 draft: A12 panel in mainline U-Boot, opt-in only.

board/powkiddy/a12-rk3128/a12-display.c drives the RK3128 VOP lite, TTL
PHY, panel GPIOs and PWM backlight. Only powkiddy-a12-display-rk3128
_defconfig (A12_UBOOT_DISPLAY=yes) enables it; the normal defconfig and DT
are unchanged. The values must match what Linux uses on the A12 today.
"""
import pathlib
import re

device = pathlib.Path(__file__).resolve().parents[1]
uboot = device / "packages/u-boot"
src = uboot / "sources"
driver = (src / "board/powkiddy/a12-rk3128/a12-display.c").read_text()
base_cfg = (src / "configs/powkiddy-a12-rk3128_defconfig").read_text().splitlines()
disp_cfg = (src / "configs/powkiddy-a12-display-rk3128_defconfig").read_text().splitlines()

# The display defconfig is the normal one plus the video options and its DT.
added = [l for l in disp_cfg if l not in base_cfg]
removed = [l for l in base_cfg if l not in disp_cfg]
assert removed == ['CONFIG_DEFAULT_DEVICE_TREE="rockchip/rk3128-powkiddy-a12-rev-a"'], removed
assert set(l for l in added if not l.startswith("#")) == {
    'CONFIG_DEFAULT_DEVICE_TREE="rockchip/rk3128-powkiddy-a12-rev-a-display"', "CONFIG_VIDEO=y",
    "CONFIG_VIDEO_LOGO=y", "CONFIG_VIDEO_BPP32=y", "CONFIG_A12_DISPLAY=y", "CONFIG_DM_PWM=y",
    "CONFIG_PWM_ROCKCHIP=y", "CONFIG_BACKLIGHT_PWM=y"}, added
assert not any("A12_DISPLAY" in l or "VIDEO" in l for l in base_cfg)
assert "obj-$(CONFIG_A12_DISPLAY) += a12-display.o" in (src / "board/powkiddy/a12-rk3128/Makefile").read_text()
mk = (uboot / "package.mk").read_text()
assert '[ "${A12_UBOOT_DISPLAY}" = "yes" ] && defconfig="powkiddy-a12-display-rk3128_defconfig"' in mk
assert 'local defconfig="powkiddy-a12-rk3128_defconfig"' in mk

# Timing equals the kernel's default 60-hblank mode (patch 0013) at 54 MHz.
patch = (device / "patches/linux/0013-a12-panel-60hz-hblank-timing.patch").read_text()
mode = re.search(r"^\+\s+\.hdisplay = 1024, \.hsync_start = (\d+), \.hsync_end = (\d+), \.htotal = (\d+),\n"
                 r"\+\s+\.vdisplay = 600, \.vsync_start = (\d+), \.vsync_end = (\d+), \.vtotal = (\d+),", patch, re.M)
assert mode, "60-hblank mode not found in patch 0013"
define = lambda name: int(re.search(rf"#define {name}\s+(\d+)", driver)[1])
assert [define(n) for n in ("A12_HSYNC_START", "A12_HSYNC_END", "A12_HTOTAL", "A12_VSYNC_START",
                            "A12_VSYNC_END", "A12_VTOTAL")] == [int(v) for v in mode.groups()]
assert 594_000 // define("A12_DCLK_DIV") == 54_000
assert round(54e6 / (define("A12_HTOTAL") * define("A12_VTOTAL")), 3) == 60.015

# Panel bus: RGB666 with dithering, rising-edge clock (patches 0003, 0008).
assert "CTRL0_OUT_MODE_P666 | CTRL0_DITHER_MODE_666 | CTRL0_DITHER_EN" in driver
assert "AXI_RGB_DCLK_POL, AXI_RGB_EN" in driver   # clock polarity bit cleared
# Panel power sequence as panel-a12 a12_prepare(): 100 ms, 60 ms, 1000 ms.
seq = re.findall(r"mdelay\((\d+)\)", driver)
assert seq[:3] == ["100", "60", "1000"], seq
# The DT carries the Linux display chain.
dts = (src / "dts/upstream/src/arm/rockchip/rk3128-powkiddy-a12-rev-a-display.dts").read_text()
linux = (device / "linux/dts/rockchip/rk3128-powkiddy-a12-rev-a.dts").read_text()
for line in ("enable-gpios = <&gpio1 RK_PB4 GPIO_ACTIVE_LOW>;", "reset-gpios = <&gpio0 RK_PD0 GPIO_ACTIVE_LOW>;",
             "pwms = <&pwm0 0 25000 0>;", "reg = <0x20038000 0x4000>, <0x10110000 0x4000>;"):
    assert line in dts and line in linux, line
pins = lambda text: re.search(r"a12_rgb_pins: rgb-pins \{\s*rockchip,pins = (.*?);", text, re.S)[1].split()
assert pins(dts) == pins(linux)
assert '#include "rk3128-powkiddy-a12-rev-a.dts"' in dts
print("u-boot display draft: ok")
