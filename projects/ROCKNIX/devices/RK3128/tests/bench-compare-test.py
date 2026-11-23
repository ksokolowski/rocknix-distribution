#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""compare.py reports per-metric ratios between two a12-bench results."""
import json
import pathlib
import subprocess
import tempfile

tool = pathlib.Path(__file__).resolve().parents[1] / "tools/bench/compare.py"
base = {"label": "knulli", "probe": {"copy_mb_s": 600.0, "read_mb_s": 900.0, "set_mb_s": 1000.0,
        "sleep_1ms_us": 1100.0, "sleep_16ms_us": 16100.0}, "core_fps": [150.0, 146.0],
        "ddr_hz": 456000000, "cpu_khz": 1200000, "gpu_hz": 480000000, "meminfo": {"MemAvailable": 100000}}
other = json.loads(json.dumps(base))
other["label"] = "rocknix"
other["probe"]["copy_mb_s"] = 400.0
other["core_fps"] = [100.0, 98.0]
other["ddr_hz"] = 300000000
with tempfile.TemporaryDirectory() as temporary:
    a, b = pathlib.Path(temporary, "a.json"), pathlib.Path(temporary, "b.json")
    a.write_text(json.dumps(base))
    b.write_text(json.dumps(other))
    out = subprocess.run(["python3", str(tool), str(a), str(b)], capture_output=True, text=True, check=True).stdout
assert "copy_mb_s" in out and "0.67" in out, out
assert "core_fps_median" in out and "0.66" in out, out
assert "ddr_hz" in out
print("bench compare: ok")
