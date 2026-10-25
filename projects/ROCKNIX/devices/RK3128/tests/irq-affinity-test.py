#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-irq-affinity moves device interrupts off CPU0 (test 57).

The GIC delivers every SPI to CPU0 by default; on the A12 that put the USB
host (network and Wi-Fi dongles), the SD controller and the PL330 DMA
(SD and audio) on one core. The script routes them by name: USB host to
CPU1, SD and DMA to CPU2. Run against a fake /proc.
"""
import os
import pathlib
import subprocess
import tempfile

device = pathlib.Path(__file__).resolve().parents[1]
src = device / "packages/a12-controls/sources"
script = src / "a12-irq-affinity"
pkg = (device / "packages/a12-controls/package.mk").read_text()
assert "a12-irq-affinity" in pkg and "enable_service a12-irq-affinity.service" in pkg
unit = (src / "a12-irq-affinity.service").read_text()
assert "ExecStart=/usr/bin/a12-irq-affinity" in unit and "Type=oneshot" in unit

INTERRUPTS = """           CPU0       CPU1       CPU2       CPU3
 26:     339547     344992     361424     337074 GIC-0  30 Level     arch_timer
 38:    1318952          0          0          0 GIC-0  32 Level     20078000.dma-controller
 39:          0          0          0          0 GIC-0  33 Level     20078000.dma-controller
 43:          0          0          0          0 GIC-0  42 Level     10180000.usb, 10180000.usb, dwc2_hsotg:usb1
 44:     381688          0          0          0 GIC-0  43 Level     ehci_hcd:usb2
 45:          0          0          0          0 GIC-0  64 Level     ohci_hcd:usb3
 52:     184594          0          0          0 GIC-0  46 Level     dw-mci
 57:          0          0          0          0 GIC-0  96 Edge      codec_hp_det
IPI0:         0          0          0          0  CPU wakeup interrupts
"""
EXPECT = {"38": "2", "39": "2", "43": "1", "44": "1", "45": "1", "52": "2"}

with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    (root / "proc").mkdir()
    (root / "proc/interrupts").write_text(INTERRUPTS)
    for irq in ("26", "38", "39", "43", "44", "45", "52", "57"):
        (root / f"proc/irq/{irq}").mkdir(parents=True)
        (root / f"proc/irq/{irq}/smp_affinity_list").write_text("0-3\n")
    env = dict(os.environ, A12_ROOT=str(root))
    out = subprocess.run(["sh", str(script)], env=env, check=True, capture_output=True, text=True).stdout
    for irq in ("26", "38", "39", "43", "44", "45", "52", "57"):
        got = (root / f"proc/irq/{irq}/smp_affinity_list").read_text().strip()
        assert got == EXPECT.get(irq, "0-3"), (irq, got, out)
    assert "44 ehci_hcd:usb2 -> 1" in out, out
print("irq affinity: ok")
