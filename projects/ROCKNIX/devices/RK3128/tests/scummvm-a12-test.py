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
for key, value in (("music_driver", "auto"), ("gfx_mode", "opengl")):
    assert re.search(rf"s/\^{key}=\.\*/{key}={value}/", svm), f"RK3128 {key}={value}"

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
assert re.search(r"^music_driver=auto$", ini, re.M) and re.search(r"^gfx_mode=opengl$", ini, re.M)
assert re.search(r"^gm_device=fluidsynth$", ini, re.M) and re.search(r"^extrapath=/storage/roms/bios$", ini, re.M)
print("scummvm a12: ok")
