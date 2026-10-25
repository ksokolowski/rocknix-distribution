#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SD DMA errors must not crash the A12.

pstore (boot before f8f51dd6, 2026-10-08): pl330 "Runtime PM usage count
underflow" and "pl330_update ... Unexpected!", then dw_mmc "Failed to get
external DMA channel" on runtime resume left host->dms NULL while DMA mode
stayed on; the reset path oopsed in dw_mci_edmac_start_dma (test 22 oopsed in
dw_mci_edmac_stop_dma the same way).
"""
import pathlib
import re

device = pathlib.Path(__file__).resolve().parents[1]
# Forbidding PL330 runtime suspend did not help (boot dc484b9b crashed the same
# way); PIO avoided the PL330 (boot aafd6216). Kernel patch 0014 fixed the
# runtime PM underflow and DMA is back (test 56, pl330-runtime-pm-test); if a
# DMA error still happens, patch 0009 below falls back to PIO instead of oopsing.
dts = (device / "linux/dts/rockchip/rk3128-powkiddy-a12-rev-a.dts").read_text()
sdmmc = re.search(r"&sdmmc\s*{(.*?)\n};", dts, re.S)[1]
assert "/delete-property/ dmas;" not in sdmmc, "SD card back in PIO"
assert not (device / "packages/a12-controls/udev.d").exists(), "ineffective PL330 power rule still shipped"

patch = (device / "patches/linux/0009-dw-mmc-pio-fallback-when-dma-init-fails.patch").read_text()
assert "drivers/mmc/host/dw_mmc.c" in patch
assert re.search(r"^\+\s*host->use_dma = TRANS_MODE_PIO;", patch, re.M), "no PIO fallback"
assert re.search(r"^-\s*return ret;", patch, re.M), "resume still fails on DMA init error"
print("sd dma robustness: ok")
