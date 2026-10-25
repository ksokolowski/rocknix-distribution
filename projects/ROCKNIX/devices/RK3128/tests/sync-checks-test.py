#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-sync-checks collects the sync branch's pending hardware evidence.

One SSH command on the A12 writes the facts BACKLOG's hardware checks need
(oomd masked, splash mode, CMA/journal/zram, SD DMA vs PIO, ES power saver)
to the diagnostics folder. Run here against a fake root and mocked tools.
"""
import os
import pathlib
import subprocess
import tempfile

device = pathlib.Path(__file__).resolve().parents[1]
script = device / "packages/a12-controls/sources/a12-sync-checks"
pkg = (device / "packages/a12-controls/package.mk").read_text()
assert "a12-sync-checks" in pkg
# Upstream protects system.slice (MemoryLow=192M, MemoryMin=64M) for oomd; on
# 225 MB the kernel then reclaims the running game first (test 55).
dropin = device / "packages/a12-controls/sources/20-a12-system-slice.conf"
assert dropin.read_text().split() == ["[Slice]", "MemoryLow=0", "MemoryMin=0"], dropin.read_text()
assert 'system.slice.d/20-a12-system-slice.conf' in pkg

with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp) / "root"
    files = {
        "proc/sys/kernel/random/boot_id": "abcd-1234\n",
        "proc/cmdline": "console=ttyS0 quiet a12_kms_splash\n",
        "proc/uptime": "42.0 100.0\n",
        "proc/meminfo": "MemTotal: 220000 kB\nMemAvailable: 90000 kB\nCmaFree: 12000 kB\n",
        "proc/interrupts": " 30: 1234 GIC mmc0\n",
        "etc/os-release": 'BUILD_ID="20261012-sync"\n',
        "sys/block/zram0/comp_algorithm": "lzo [lzo-rle] lz4 zstd\n",
        "sys/block/zram0/recomp_algorithm": "#1: lzo lzo-rle lz4 [zstd]\n",
        "sys/block/zram0/mm_stat": "1000 400 500 0 600 0 0 0 0\n",
        "sys/class/power_supply/battery/capacity": "77\n",
        "sys/fs/cgroup/system.slice/memory.low": "0\n",
        "sys/fs/cgroup/system.slice/memory.min": "0\n",
        "storage/.cache/a12-splash/boot-seconds": "21.4\n",
        "storage/.config/emulationstation/es_settings.cfg":
            '<config><string name="PowerSaverMode" value="enhanced"/></config>\n',
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    (root / "run/log/journal").mkdir(parents=True)
    bindir = pathlib.Path(tmp) / "bin"
    bindir.mkdir()
    mocks = {
        "systemctl": 'case "$*" in *is-enabled*oomd*) echo masked;; *ActiveState*games.slice*) echo active;; *) :;; esac',
        "journalctl": "echo 'a12-splash: started'",
        "systemd-analyze": "echo 'Startup finished in 3s (kernel) + 22s (userspace)'",
        "dmesg": "echo 'dwmmc_rockchip 10214000.mmc: using PIO mode'",
        "top": ":", "sync": ":",
    }
    for name, body in mocks.items():
        (bindir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bindir / name).chmod(0o755)
    env = dict(os.environ, A12_ROOT=str(root), PATH=f"{bindir}:/usr/bin:/bin")
    out = subprocess.run(["sh", str(script)], env=env, check=True, capture_output=True, text=True).stdout.strip()
    report = pathlib.Path(out).read_text()
    assert out.endswith("/storage/.cache/a12-diagnostics/sync-checks-abcd-1234.txt"), out
    for expected in ('BUILD_ID="20261012-sync"', "systemd-oomd: masked", "games.slice: active",
                     "/sys/fs/cgroup/system.slice/memory.low: 0", "/sys/fs/cgroup/system.slice/memory.min: 0",
                     "fbdev: absent", "a12_kms_splash: on", "boot-seconds: 21.4",
                     "CmaFree: 12000 kB", "[zstd]", "SD mode: PIO", "using PIO mode",
                     'name="PowerSaverMode" value="enhanced"', "Startup finished"):
        assert expected in report, (expected, report)
print("sync checks: ok")
