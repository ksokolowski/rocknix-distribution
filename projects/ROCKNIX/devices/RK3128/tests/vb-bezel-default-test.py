#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 image shows Virtual Boy without a bezel (owner, 2026-10-21, test 73).

The Bezel Project bezel for Virtual Boy (global.bezel=thebezelproject)
drew a monitor frame that covered the picture. The A12's system.cfg sets
virtualboy.bezel=none (RK3128 only); every other system keeps the global
setting.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
mk = (root / "projects/ROCKNIX/packages/rocknix/package.mk").read_text()
cfg = (root / "projects/ROCKNIX/packages/rocknix/config/system/configs/system.cfg").read_text()
assert "virtualboy.bezel" not in cfg  # shared default unchanged

block = re.search(r'if \[ "\$\{DEVICE\}" = "RK3128" \]; then\n(.*?)\n  fi\n', mk, re.S)[1]
lines = [l.strip() for l in block.splitlines() if "virtualboy.bezel" in l]
assert len(lines) == 1, block
with tempfile.TemporaryDirectory() as tmp:
    conf = pathlib.Path(tmp) / "usr/config/system/configs/system.cfg"
    conf.parent.mkdir(parents=True)
    conf.write_text(cfg)
    subprocess.run(["bash", "-c", lines[0]], env={"INSTALL": tmp, "PATH": "/usr/bin:/bin"}, check=True)
    out = conf.read_text()
    assert out.count("virtualboy.bezel=none\n") == 1, out[-200:]
    assert [l for l in out.splitlines() if l.startswith("global.bezel")] == \
           [l for l in cfg.splitlines() if l.startswith("global.bezel")]
print("vb bezel default: ok")
