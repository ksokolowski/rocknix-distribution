#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""powerstate.sh polls the battery without starting processes.

Every 2 s it ran `cat` and `awk` in command substitutions and `sleep 2`:
about five new processes per round. New tasks start with a high load
estimate, so schedutil held the A12 at 1200 MHz with ES idle (2026-10-28).
The loop now reads with `read` and waits with `read -t` on a FIFO.

A copy of the script runs against a fake power_supply directory and a stub
/etc/profile under strace: a status change still switches the mode, and
3 s of steady polling start no process.

On the A12 powerstate starts before a12-battery registers, so the battery
directory appears only after the script is running; looked up once, it was
never found and every round logged "No such file" (2026-10-28). Here the
directory appears 1.5 s after start, and stderr must stay empty.
"""
import os
import signal
import pathlib
import re
import shutil
import subprocess
import tempfile
import time

root = pathlib.Path(__file__).resolve().parents[5]
script = (root / "projects/ROCKNIX/packages/sysutils/powerstate/sources/powerstate.sh").read_text()

if not shutil.which("strace"):
    print("SKIP powerstate-fork-test (no strace)")
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as tmp:
    t = pathlib.Path(tmp)
    (t / "sys/class/power_supply").mkdir(parents=True)
    bat = t / "sys/class/power_supply/battery"
    log = t / "calls.log"
    (t / "profile").write_text(f"""
log() {{ echo "log $*" >> {log}; }}
get_setting() {{ :; }}
ledcontrol() {{ :; }}
gpu_performance_level() {{ echo "gpu $1" >> {log}; }}
battery_percent() {{ awk 'BEGIN {{FS="="}} /POWER_SUPPLY_CAPACITY=/ {{print $2}}' {t}/sys/class/power_supply/[Bb][Aa][Tt]*/uevent; }}
""")
    # /tmp/ first: the temporary directory itself lives in /tmp.
    body = script.replace("/tmp/", f"{t}/tmp-")
    body = body.replace("/sys/class/power_supply", f"{t}/sys/class/power_supply")
    body = body.replace(". /etc/profile", f". {t}/profile")
    (t / "powerstate.sh").write_text(body)
    trace = t / "trace"
    err = open(t / "stderr", "w")
    p = subprocess.Popen(["strace", "-f", "-qq", "-tt", "-e", "trace=clone,clone3,fork,vfork",
                          "-o", str(trace), "bash", str(t / "powerstate.sh")],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                         start_new_session=True)
    try:
        time.sleep(1.5)
        bat.mkdir()
        (bat / "capacity").write_text("80\n")
        (bat / "uevent").write_text("POWER_SUPPLY_CAPACITY=80\n")
        (bat / "status").write_text("Discharging\n")
        time.sleep(2.5)
        mark = time.strftime("%H:%M:%S")
        time.sleep(3.2)
    finally:
        os.killpg(p.pid, signal.SIGKILL)
        p.wait(timeout=5)
    err.close()
    calls = log.read_text() if log.exists() else ""
    errors = (t / "stderr").read_text()
    assert not errors, errors
    assert "log" in calls and "Switching to battery mode." in calls, calls
    lines = [l for l in trace.read_text().splitlines() if re.search(r"\b(clone3?|v?fork)\(", l)]
    steady = [l for l in lines if l.split()[1][:8] >= mark]
    assert not steady, f"{len(steady)} processes started while polling:\n" + "\n".join(steady[:6])
print("powerstate fork: ok")
