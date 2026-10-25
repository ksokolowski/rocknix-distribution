#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""VLC uses ALSA on the A12 (owner, 2026-10-12: ALSA everywhere).

The A12 runs ALSA only (no PulseAudio server, tests 39-40), but VLC was
built with --enable-pulse --disable-alsa, so ES's preview videos had no
usable audio output. On RK3128 VLC depends on alsa-lib and is configured
with --enable-alsa --disable-pulse; other devices keep PulseAudio.
"""
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
pkg = root / "projects/ROCKNIX/packages/multimedia/vlc/package.mk"


def configure(device):
    script = f"""
DEVICE={device}; ARCH=arm; TOOLCHAIN=/t; OPENGLES=mesa
. "{pkg}"
pre_configure_target
echo "DEPS=$PKG_DEPENDS_TARGET"
echo "OPTS=$PKG_CONFIGURE_OPTS_TARGET"
"""
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout
    vals = dict(line.split("=", 1) for line in out.splitlines() if line[:5] in ("DEPS=", "OPTS="))
    return vals["DEPS"].split(), vals["OPTS"].split()


deps, opts = configure("RK3128")
assert "--enable-alsa" in opts and "--disable-alsa" not in opts, opts
assert "--disable-pulse" in opts and "--enable-pulse" not in opts, opts
assert "alsa-lib" in deps and "pulseaudio" not in deps, deps

deps, opts = configure("RK3326")
assert "--enable-pulse" in opts and "--disable-alsa" in opts, opts
assert "pulseaudio" in deps, deps
print("vlc alsa: ok")
