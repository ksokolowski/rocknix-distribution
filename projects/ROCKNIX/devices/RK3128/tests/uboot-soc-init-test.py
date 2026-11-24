#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Mainline U-Boot repeats the vendor RK3128 arch_cpu_init SoC settings.

Test 32 (2026-10-10): with mainline U-Boot the LCDC QoS priority register
(0x1012f188) read 0x5 instead of the vendor 0x30f; under memory load at DDR
456 MHz Final Fight showed flickering black vertical lines. Writing the vendor
value live removed them. caesar-u-boot 9724e7aa
arch/arm/mach-rockchip/rk3128/rk3128.c arch_cpu_init sets the MSCH read
latency, the LCDC QoS priority and GPIO1C1 as GPIO.

Test 37 (2026-10-11): on the A12 the GPIO1C1 write stops a cold power-on
(black screen; warm reboots were unaffected), alone or with the other writes.
The QoS write alone cold-boots and keeps Final Fight clean. The MSCH read
latency is already 0x3f before U-Boot. Only the QoS write is ported.
"""
import pathlib
import re

device = pathlib.Path(__file__).resolve().parents[1]
patch = (device / "packages/u-boot/patches/0005-rk3128-vendor-soc-init.patch").read_text()
added = "\n".join(l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))

assert re.search(r"^\+obj-y \+= rk3128\.o$", patch, re.M), "rk3128.c not built"
assert "+++ b/arch/arm/mach-rockchip/rk3128/rk3128.c" in patch
assert re.search(r"int arch_cpu_init\(void\)\n\{", added), "no arch_cpu_init"
assert re.search(r"#define QOS_LCDC_PRIORITY\s+0x1012f188", added)
assert re.search(r"writel\(QOS_PRIORITY_LEVEL\(3, 3\), QOS_LCDC_PRIORITY\);", added)
assert "gpio1c_iomux" not in added and "rk_clrsetreg" not in added, "GPIO1C1 write breaks A12 cold boot (test 37)"
assert "0x10128014" not in added and added.count("writel(") == 1, "only the cold-boot-verified QoS write is ported"
assert re.search(r"#define QOS_PRIORITY_LEVEL\(h, l\)\s+\\\n\s+\(\(\(\(h\) & 3\) << 8\) \| \(\(\(h\) & 3\) << 2\) \| \(\(l\) & 3\)\)", added)


def level(h, l):
    return ((h & 3) << 8) | ((h & 3) << 2) | (l & 3)


assert level(3, 3) == 0x30f
# The register implements four bits; the hardware reads 0x30f back as 0xf.
assert level(3, 3) & 0xf == 0xf
print("u-boot soc init: ok")
