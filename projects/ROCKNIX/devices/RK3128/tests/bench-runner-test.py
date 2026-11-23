#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-bench emits valid JSON with the core FPS list and never calls `paste`.

On ROCKNIX /usr/bin/paste uploads its input to dpaste.com, and busybox has no
coreutils paste; test 23's baseline produced pastebin error text as core_fps.
"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

runner = pathlib.Path(__file__).resolve().parents[1] / "tools/bench/a12-bench"
with tempfile.TemporaryDirectory(prefix="a12-bench-") as temporary:
    root = pathlib.Path(temporary)
    shutil.copy(runner, root / "a12-bench")
    (root / "a12-perfprobe").write_text('#!/bin/sh\necho \'{"copy_mb_s": 468.0, "set_mb_s": 817.6, "read_mb_s": 501.5, '
                                         '"sleep_1ms_us": 1119.6, "sleep_16ms_us": 16158.8, "sink": 0}\'\n')
    (root / "core-benchmark").write_text('#!/bin/sh\necho "[FBNeo] noise"\n'
                                          'echo "frames 1200-1800 in 4.000 s = 150.00 FPS; target 59.63 FPS"\n'
                                          'echo "frames 1800-2400 in 4.100 s = 146.34 FPS; target 59.63 FPS"\n')
    fake_bin = root / "bin"
    fake_bin.mkdir()
    marker = root / "paste-called"
    (fake_bin / "paste").write_text('#!/bin/sh\ntouch "%s"\necho "{\\"errors\\": []}.txt"\n' % marker)
    for path in (root / "a12-bench", root / "a12-perfprobe", root / "core-benchmark", fake_bin / "paste"):
        path.chmod(0o755)
    env = dict(os.environ, PATH=f"{fake_bin}:/usr/bin:/bin", A12_BENCH_OUT=str(root))
    subprocess.run(["sh", str(root / "a12-bench"), "unit", "core.so", "rom.zip"], env=env, check=True,
                   capture_output=True)
    assert not marker.exists(), "a12-bench called paste (uploads data on ROCKNIX)"
    data = json.loads((root / "a12-bench-unit.json").read_text())
    assert data["core_fps"] == [150.0, 146.34], data["core_fps"]
    assert data["probe"]["copy_mb_s"] == 468.0
print("bench runner: ok")
