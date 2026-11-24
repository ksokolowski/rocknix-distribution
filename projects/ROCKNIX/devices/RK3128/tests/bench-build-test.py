#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""build.sh refuses to build a probe that may not run on KNULLI's 4.4 kernel."""
import os
import pathlib
import subprocess
import tempfile

bench = pathlib.Path(__file__).resolve().parents[1] / "tools/bench"
env = {key: value for key, value in os.environ.items() if key != "PROBE_CC"}
with tempfile.TemporaryDirectory() as temporary:
    result = subprocess.run(["bash", str(bench / "build.sh"), temporary], env=env,
                            capture_output=True, text=True)
assert result.returncode != 0, "build.sh accepted a missing PROBE_CC"
assert "PROBE_CC" in result.stderr, result.stderr
# A failed clock read must not turn into a plausible-looking bandwidth number.
assert "clock_gettime(CLOCK_MONOTONIC, &t) != 0" in (bench / "a12-perfprobe.c").read_text()
# RetroArch is linked with an executable stack (RWE) and glibc 2.44 refuses to
# dlopen RWE cores (Cyclone ARM assembly) into an RW process; mirror RetroArch.
assert "-Wl,-z,execstack" in (bench / "build.sh").read_text(), "core-benchmark cannot load execstack cores"
print("bench build guard: ok")
