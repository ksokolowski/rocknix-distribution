#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""ScummVM on the A12: light music, GPU scaling, NEON, no PipeWire (2026-11-12).

Day of the Tentacle's intro, silent (SDL dummy audio), 20 s after 20 s:
FluidSynth with reverb and chorus took 56 % of a core (its audio thread
46 %) and 88 MB RSS; AdLib with OpenGL 12 % and 57 MB. So gfx_mode=opengl is the A12
default, music is auto: MT-32 games get Munt with the owner's ROMs
(mt32-seed-test.py), General MIDI games FluidSynth (owner 2026-11-19: best
sound first, optimise later), the rest AdLib.
ScummVM's configure leaves SCUMMVM_NEON off on 32-bit ARM, so its NEON
blitters were not built. Nothing on the A12 uses PipeWire
(PIPEWIRE_SUPPORT="no"), but scummvm-sa depended on it and RetroArch's
configure then found it in the sysroot and linked it.
"""
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
pk = root / "projects/ROCKNIX/packages"
svm = (pk / "emulators/standalone/scummvm-sa/package.mk").read_text()
ra = (pk / "emulators/libretro/retroarch/package.mk").read_text()

deps = re.search(r'^PKG_DEPENDS_TARGET="([^"]*)"', svm, re.M)[1].split()
assert "pipewire" not in deps, "scummvm-sa does not link PipeWire"
assert re.search(r'PIPEWIRE_SUPPORT}" = "yes" \]; then\n\s+PKG_DEPENDS_TARGET\+=" pipewire"', svm), "only with PipeWire support"
assert "--enable-ext-neon" in svm, "NEON blitters on 32-bit ARM"
flag = ra.find('PKG_CONFIGURE_OPTS_TARGET+=" --disable-pipewire"')
assign = ra.find('PKG_CONFIGURE_OPTS_TARGET="')
assert flag > assign >= 0, "RetroArch: --disable-pipewire after the options are assigned (first build put it before)"
assert re.search(r"s/\^music_driver=\.\*/music_driver=auto/", svm), "RK3128 music_driver=auto"
# HQ3x on the CPU for 320-wide games (test 95; ScummVM lowers the factor for
# wider ones, 3D games switch to OpenGL by themselves).
for setting in ("scaler=xbrf", "scale_factor=3"):
    assert setting in svm, f"RK3128 {setting}"
# xBRF (the owner's xBR-family scaler, laetoli-engine, GPL-3.0-or-later) as a
# ScummVM scaler plugin: changed rectangles with a 2-pixel border (test 99).
patch = (root / "projects/ROCKNIX/devices/RK3128/patches/scummvm-sa/0002-xbrf-scaler.patch").read_text()
assert "REGISTER_PLUGIN_STATIC(XBRF, PLUGIN_TYPE_SCALER, XBRFPlugin)" in patch
assert "+\t\tLINK_PLUGIN(XBRF)" in patch, "linked in base/plugins.cpp"
assert "uint extraPixels() const override { return kBorder; }" in patch and "const int kBorder = 2;" in patch
for f in ("xbrf.cpp", "xbrf_patterns.cpp", "parallel_rows.cpp"):
    head = patch.split(f"+++ b/graphics/scaler/xbrf/presentation/enhance/{f}\n", 1)[1][:400]
    assert "GPL-3.0-or-later" in head and "Krzysztof Soko" in head, f"{f} keeps its licence and author"
assert "gfx_mode=opengl" not in svm, "the software renderer runs the scaler"
# The A12 mixes at 48 kHz (dmix): ScummVM at 44.1 kHz went through ALSA's linear
# resampler. 48 kHz costs FluidSynth 2 points, resampling cost 0.6 (test 93).
assert "output_rate=48000" in svm, "RK3128 output_rate=48000"

system = root / "build.ROCKNIX-RK3128.arm/image/system"
if not system.is_dir():
    print("scummvm a12: ok (SKIP image: not built)")
    raise SystemExit(0)
linked = []
for f in list(system.glob("usr/bin/*")) + list(system.rglob("*.so*")):
    if f.is_file() and not f.is_symlink():
        out = subprocess.run(["readelf", "-d", str(f)], capture_output=True, text=True).stdout
        if "libpipewire" in out:
            linked.append(str(f.relative_to(system)))
assert not linked, "links PipeWire:\n" + "\n".join(sorted(linked))
ini = (system / "usr/config/scummvm/scummvm.ini").read_text()
if not re.search(r"^scaler=xbrf$", ini, re.M):
    print("scummvm a12: ok (SKIP image ini: older than the xBRF default, rebuild scummvm-sa)")
    raise SystemExit(0)
assert re.search(r"^music_driver=auto$", ini, re.M) and re.search(r"^gfx_mode=surfacesdl$", ini, re.M)
assert re.search(r"^scaler=xbrf$", ini, re.M) and re.search(r"^scale_factor=3$", ini, re.M)
assert re.search(r"^output_rate=48000$", ini, re.M)
assert re.search(r"^gm_device=fluidsynth$", ini, re.M) and re.search(r"^extrapath=/storage/roms/bios$", ini, re.M)
print("scummvm a12: ok")
