#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""FluidSynth on the A12: no PipeWire, single precision with NEON, samples on demand (test 93).

perf in Day of the Tentacle's intro: per-voice interpolation 28 %, mixing
27 % and filtering 19 % of the time, all scalar float code. FluidSynth
mixes in double unless enable-floats is on, and GCC vectorises float loops
with NEON on 32-bit ARM only with -funsafe-math-optimizations (NEON
flushes denormals). Both: its audio thread 43 -> 36 % in DOTT, 20 -> 16 %
in Sam & Max. Several render threads (synth.cpu-cores) cost more in total
(2: 56 %, 4: 70 %), so they stay off.
The package enabled PipeWire and PulseAudio unconditionally: a rebuild
linked libpipewire, which the A12 does not ship, and ScummVM would not
start. ScummVM does not expose synth.dynamic-sample-loading: an A12 patch
sets it, so only the instruments a game uses are kept in RAM (about 8 MB
less in DOTT).
"""
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
mk = root / "projects/ROCKNIX/packages/audio/fluidsynth/package.mk"


def evaluate(device, pipewire):
    """Source the package as the build does; return its CMake options and the CFLAGS configure sees."""
    script = f'''
ROOT={root}; DEVICE={device}; PIPEWIRE_SUPPORT={pipewire}; TARGET_ARCH=arm
CFLAGS="-O2"; CXXFLAGS="-O2"
. "{mk}"
declare -F pre_configure_target >/dev/null && pre_configure_target
printf '%s\\n' "$PKG_CMAKE_OPTS_TARGET" "CFLAGS=$CFLAGS" "CXXFLAGS=$CXXFLAGS"
'''
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout


a12 = evaluate("RK3128", "no")
assert "-Denable-pipewire=0" in a12 and "-Denable-pulseaudio=0" in a12, f"no PipeWire or PulseAudio on the A12:\n{a12}"
assert "-Denable-floats=1" in a12, f"single precision on the A12:\n{a12}"
assert re.search(r"^CFLAGS=.*-funsafe-math-optimizations", a12, re.M), f"NEON for float loops:\n{a12}"

other = evaluate("RK3566", "yes")
assert "-Denable-pipewire=1" in other and "-Denable-pulseaudio=1" in other, f"PipeWire devices keep it:\n{other}"
assert "enable-floats" not in other and "unsafe-math" not in other, f"other devices unchanged:\n{other}"

patches = sorted((root / "projects/ROCKNIX/devices/RK3128/patches/scummvm-sa").glob("*.patch"))
assert patches, "ScummVM patch for dynamic sample loading"
text = "".join(p.read_text() for p in patches)
assert re.search(r'^\+.*"synth\.dynamic-sample-loading", 1', text, re.M), "the patch enables it"

for src in root.glob("build.ROCKNIX-RK3128.arm/build/scummvm-sa-*/audio/softsynth/fluidsynth.cpp"):
    code = src.read_text()
    assert 0 <= code.find("synth.dynamic-sample-loading") < code.find("new_fluid_synth(_settings)"), \
        f"set before the synth is created: {src}"
print("fluidsynth a12: ok")
