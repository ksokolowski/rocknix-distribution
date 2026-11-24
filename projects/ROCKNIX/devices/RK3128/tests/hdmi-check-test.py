#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""055-hdmi-check lists the DRM modes only when it uses them.

The script writes /var/run/drmMode and drmConn, which RetroArch and SDL2
read. Only a 1280- or 1920-wide fbdev mode needs a mode from drm_tool; any
other screen gets 0 and 1. It ran drm_tool twice first on every device:
1.3 s of each A12 boot, where there is no fb0 at all (test 92).
"""
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
hook = root / "projects/ROCKNIX/packages/rocknix/autostart/055-hdmi-check"


def run(fb_modes):
    """Run the hook with fake fbdev modes; return (drmMode, drmConn, drm_tool calls)."""
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        (t / "run").mkdir()
        modes = t / "fb0-modes"
        if fb_modes is not None:
            modes.write_text(fb_modes + "\n")
        log = t / "drm_tool.log"
        log.write_text("")
        tool = t / "drm_tool"
        tool.write_text(f'#!/bin/sh\necho call >> "{log}"\n'
                        'printf "mode 41: 1920x1080 60Hz\\nmode 7: 1280x720 60Hz\\n"\n')
        tool.chmod(0o755)
        script = (hook.read_text()
                  .replace("/sys/class/graphics/fb0/modes", str(modes))
                  .replace("/usr/bin/drm_tool", str(tool))
                  .replace("/var/run/", f"{t}/run/"))
        subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                       env={"PATH": os.environ["PATH"]}, check=True)
        read = lambda n: (t / "run" / n).read_text().strip() if (t / "run" / n).exists() else None
        return read("drmMode"), read("drmConn"), len(log.read_text().split())


mode, conn, calls = run(None)
assert (mode, conn) == ("0", "1"), f"no fb0 (the A12): {mode!r} {conn!r}"
assert calls == 0, f"no fb0, yet drm_tool ran {calls} times"

mode, conn, calls = run("U:1024x600p-60")
assert (mode, conn, calls) == ("0", "1", 0), (mode, conn, calls)

mode, conn, calls = run("U:1280x720p-60")
assert mode == "7" and calls >= 1, f"720p takes the 1280x720 mode: {mode!r}"

mode, conn, calls = run("U:1920x1080p-60")
assert conn == "41" and calls >= 1, f"1080p takes the 1920x1080 mode: {conn!r}"

print("hdmi check: ok")
