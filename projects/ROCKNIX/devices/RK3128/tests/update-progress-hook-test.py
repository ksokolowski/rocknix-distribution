#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Initramfs progress meters also draw on KMS when a12-update-splash exists (test 61).

Without fbdev (A12_NO_FBDEV) the initramfs console is invisible, so an
update showed nothing for ≈5 minutes. ProgressTask_Percent/_Spinner in the
shared busybox `functions` call ${A12_UPDATE_SPLASH} (A12 initramfs only)
with the message and percent, at most about once a second and once at the
end; other devices have no such binary and are unaffected.
"""
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
functions = (root / "projects/ROCKNIX/packages/sysutils/busybox/scripts/functions").read_text()

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    log = tmp / "calls"
    tool = tmp / "a12-update-splash"
    tool.write_text(f'#!/bin/sh\necho "$1|$2" >> {log}\n')
    tool.chmod(0o755)
    (tmp / "progress").mkdir()
    target = tmp / "SYSTEM"
    script = functions.replace("/dev/.progress", str(tmp / "progress")) + f'''
usleep() {{ sleep 0.05; }}
echo > {tmp}/progress/run
ProgressTask_Percent "Updating System..." {target} 1000 > /dev/null &
for n in 100 300 600 1000; do head -c $n /dev/zero > {target}; sleep 0.3; done
echo done > {tmp}/progress/stop
wait
echo > {tmp}/progress/run
rm -f {tmp}/progress/stop
ProgressTask_Spinner "Checking disk..." > /dev/null &
sleep 0.3; echo ok > {tmp}/progress/stop; wait
'''
    env = dict(os.environ, A12_UPDATE_SPLASH=str(tool))
    subprocess.run(["bash", "-c", script], env=env, check=True, timeout=30)
    calls = log.read_text().splitlines()
    percent = [c for c in calls if c.startswith("Updating System...|")]
    assert percent and percent[-1] == "Updating System...|100", calls
    values = [int(c.split("|")[1]) for c in percent]
    assert values == sorted(values) and values[0] < 100, values
    assert len(percent) <= 8, calls  # throttled (polls every 0.05 s here)
    assert any(c == "Checking disk...|" for c in calls), calls

    # Without the tool (other devices) nothing is called and output is unchanged.
    log.unlink()
    env = dict(os.environ, A12_UPDATE_SPLASH=str(tmp / "missing"))
    subprocess.run(["bash", "-c", script], env=env, check=True, timeout=30)
    assert not log.exists()
print("update progress hook: ok")
