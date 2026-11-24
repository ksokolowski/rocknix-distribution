#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Mainline U-Boot programs CPLL and GPLL exactly like the vendor bootloader.

Test 30 (2026-10-10): with mainline U-Boot 2026.07 the A12 kept GPLL at
refdiv 2 / VCO 1188 MHz (CRU 0x30/0x34 = 0x2063/0x1442) and CPLL at the
pre-U-Boot 500 MHz with VCO 500 MHz (0x107d/0x1446); a held image shook under
memory load and games showed black vertical lines. The vendor bootloader
(KNULLI, caesar-u-boot clk_rk3128.c rkclk_init and its rk3128_pll_rates)
leaves GPLL 0x4063/0x1441 and CPLL 0x6064/0x1441, and the display was clean.
"""
import pathlib
import re

device = pathlib.Path(__file__).resolve().parents[1]
patch = (device / "packages/u-boot/patches/0004-rk3128-vendor-pll-configuration.patch").read_text()
assert "drivers/clk/rockchip/clk_rk3128.c" in patch
assert re.search(r"^\+static const struct pll_div gpll_init_cfg = PLL_DIVISORS\(GPLL_HZ, 1, 4, 1\);$", patch, re.M), \
    "GPLL not at the vendor refdiv 1 / postdiv1 4"
assert re.search(r"^-static const struct pll_div gpll_init_cfg = PLL_DIVISORS\(GPLL_HZ, 2, 2, 1\);$", patch, re.M)
assert re.search(r"^\+static const struct pll_div cpll_init_cfg = PLL_DIVISORS\(400 \* MHz, 1, 6, 1\);$", patch, re.M), \
    "CPLL not at the vendor 400 MHz configuration"
assert re.search(r"^\+.*rkclk_set_pll\(cru, CLK_CODEC, &cpll_init_cfg\)", patch, re.M), "CPLL never programmed"
assert re.search(r"^\+.*CPLL_MODE_SLOW << CPLL_MODE_SHIFT", patch, re.M), "CPLL reprogrammed while in normal mode"


def words(hz, refdiv, postdiv1, postdiv2):
    """CRU PLL_CON0/1 low halves as PLL_DIVISORS and rkclk_set_pll produce them."""
    fbdiv = hz * refdiv * postdiv1 * postdiv2 // 24_000_000
    vco = 24_000_000 * fbdiv // refdiv
    assert 600_000_000 <= vco <= 2_400_000_000, vco
    con0 = postdiv1 << 12 | fbdiv
    con1 = 1 << 12 | postdiv2 << 6 | refdiv  # DSMPD (integer mode) | postdiv2 | refdiv
    return con0, con1, vco


assert words(594_000_000, 1, 4, 1)[:2] == (0x4063, 0x1041), words(594_000_000, 1, 4, 1)
assert words(400_000_000, 1, 6, 1)[:2] == (0x6064, 0x1041), words(400_000_000, 1, 6, 1)
# The captured 0x1441 adds the read-only LOCK bit (bit 10) to 0x1041.
assert 0x1441 & ~(1 << 10) == 0x1041
print("u-boot pll config: ok")
