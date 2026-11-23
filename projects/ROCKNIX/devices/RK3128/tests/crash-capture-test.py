#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""ramoops is reserved in the DTS and save-report archives then clears pstore."""
import os
import pathlib
import re
import subprocess
import tempfile

device = pathlib.Path(__file__).resolve().parents[1]
dts = (device / "linux/dts/rockchip/rk3128-powkiddy-a12-rev-a.dts").read_text()
match = re.search(r'compatible = "ramoops";\s*reg = <(0x[0-9a-f]+) (0x[0-9a-f]+)>;', dts)
assert match, "ramoops node missing"
start, size = int(match[1], 16), int(match[2], 16)
assert start + size <= 0x68300000, "overlaps U-Boot FDT load address"
assert start >= 0x64000000, "too close to the kernel load area"
assert re.search(r"&watchdog\s*{\s*status = \"okay\";", dts), "watchdog not enabled"
options = (device / "options").read_text()
assert "panic=10" in options
# Oopses must become panics so ramoops captures them and panic=10 reboots.
assert "oops=panic" in options, "oops does not panic"
watchdog = (device / "packages/a12-controls/sources/10-a12-watchdog.conf").read_text()
# A swap stall during play must not hard-reset; a hung poweroff must not reboot.
assert "RuntimeWatchdogSec=90s" in watchdog, watchdog
assert "RebootWatchdogSec=off" in watchdog, watchdog
config = (device / "linux/linux.arm.conf").read_text()
for option in ("CONFIG_MAGIC_SYSRQ=y", "CONFIG_PSTORE_CONSOLE=y", "CONFIG_PSTORE_RAM=y",
               "CONFIG_SOFTLOCKUP_DETECTOR=y", "CONFIG_BOOTPARAM_SOFTLOCKUP_PANIC=1",
               "CONFIG_DETECT_HUNG_TASK=y"):
    assert option + "\n" in config, option

script = device / "packages/a12-controls/sources/a12-save-report"
with tempfile.TemporaryDirectory(prefix="a12-pstore-") as temporary:
    root = pathlib.Path(temporary)
    pstore, output, bin_dir = root / "pstore", root / "diag", root / "bin"
    pstore.mkdir()
    bin_dir.mkdir()
    (pstore / "dmesg-ramoops-0").write_text("sysrq triggered crash\n")
    for name, body in {"a12-hardware-report": "echo hw", "systemctl": "exit 0",
                       "dmesg": "exit 0", "journalctl": "exit 0", "sync": "exit 0"}.items():
        (bin_dir / name).write_text("#!/bin/sh\n" + body + "\n")
        (bin_dir / name).chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}:/usr/bin:/bin", A12_PSTORE_DIR=str(pstore),
               A12_DIAGNOSTICS_DIR=str(output), A12_HARDWARE_REPORT=str(bin_dir / "a12-hardware-report"),
               A12_BOOT_ID="test-boot")
    subprocess.run(["sh", str(script), "boot"], env=env, check=True)
    saved = output / "pstore-test-boot" / "dmesg-ramoops-0"
    assert saved.read_text() == "sysrq triggered crash\n"
    assert not any(pstore.iterdir()), "pstore record not cleared"
print("crash capture: ok")
