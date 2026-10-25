#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-deploy backs up and verifies the boot payload before uploading and rebooting."""
import os
import pathlib
import subprocess
import tempfile

tool = pathlib.Path(__file__).resolve().parents[1] / "tools/a12-deploy"
with tempfile.TemporaryDirectory() as temporary:
    tar = pathlib.Path(temporary, "ROCKNIX-RK3128.arm-test.tar")
    tar.write_bytes(b"x")
    out = subprocess.run(["bash", str(tool), "--dry-run", str(tar)], capture_output=True, text=True, check=True,
                         env=dict(os.environ, A12_HOST="192.0.2.1")).stdout
lines = out.splitlines()
backup = next(i for i, line in enumerate(lines) if "cp /flash/KERNEL" in line)
upload = next(i for i, line in enumerate(lines) if "/storage/.update/" in line)
reboot = next(i for i, line in enumerate(lines) if line.strip().endswith("reboot"))
assert backup < upload < reboot, out
assert any("sha256sum -c" in line for line in lines), out
assert "/flash/KERNEL.md5" in lines[backup] and "/flash/SYSTEM.md5" in lines[backup], out
rollback = (tool.parent / "a12-rollback-from-card").read_text()
assert "KERNEL.md5" in rollback and "SYSTEM.md5" in rollback, "rollback drops md5 files"
print("deploy plan: ok")
