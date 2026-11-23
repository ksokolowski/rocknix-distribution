#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare two a12-bench JSON files: compare.py BASELINE.json CANDIDATE.json"""
import json
import statistics
import sys


def metrics(data):
    values = {key: data["probe"][key] for key in sorted(data["probe"]) if key != "sink"}
    if data.get("core_fps"):
        values["core_fps_median"] = statistics.median(data["core_fps"])
    for key in ("ddr_hz", "cpu_khz", "gpu_hz"):
        values[key] = data.get(key, 0)
    values["MemAvailable_kB"] = data.get("meminfo", {}).get("MemAvailable", 0)
    return values


a, b = (json.load(open(path)) for path in sys.argv[1:3])
ma, mb = metrics(a), metrics(b)
print(f"{'metric':<20} {a['label']:>14} {b['label']:>14} {'B/A':>7}")
for key in ma:
    ratio = mb.get(key, 0) / ma[key] if ma[key] else float("nan")
    print(f"{key:<20} {ma[key]:>14.1f} {mb.get(key, 0):>14.1f} {ratio:>7.2f}")
