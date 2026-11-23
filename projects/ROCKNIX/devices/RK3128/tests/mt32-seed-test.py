#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""ScummVM uses Roland MT-32 music when the owner's ROMs are there (2026-11-19).

Games written for the MT-32 (Fate of Atlantis, Monkey Island 1-2 floppy,
Loom EGA, Sierra) ask ScummVM's auto selection for the device in
mt32_device. With the ROMs in the BIOS folder Munt plays them (Atlantis
intro: 33 % of a core on the audio thread, about 2 MB more than AdLib;
FluidSynth took 46 % and 37 MB). Without the ROMs, mt32_device=mt32 left
the game with no music at all, so 022-a12-bios sets it to mt32 only when
both ROMs are present and back to null otherwise; any other value the
owner chose is left alone. The ROMs are Roland firmware, never in the image.
"""
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
script = root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/sources/022-a12-bios"
INI = "[scummvm]\nmusic_driver=auto\ngfx_mode=opengl\n\n[atlantis]\nengineid=scumm\n"


def run(tmp, ini, roms):
    t = pathlib.Path(tmp)
    bios = t / "storage/roms/bios"
    bios.mkdir(parents=True, exist_ok=True)
    for name in ("MT32_CONTROL.ROM", "MT32_PCM.ROM"):
        (bios / name).unlink(missing_ok=True)
        if name in roms:
            (bios / name).write_bytes(b"rom")
    conf = t / "storage/.config/scummvm/scummvm.ini"
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(ini)
    subprocess.run(["bash", str(script)], env={"A12_ROOT": tmp, "PATH": "/usr/bin:/bin"}, check=True)
    return conf.read_text()


def device(text):
    head = text.split("\n[", 1)[0]
    return [l.split("=", 1)[1] for l in head.splitlines() if l.startswith("mt32_device=")]


with tempfile.TemporaryDirectory() as tmp:
    both = ("MT32_CONTROL.ROM", "MT32_PCM.ROM")
    out = run(tmp, INI, both)
    assert device(out) == ["mt32"], out
    assert "[atlantis]\nengineid=scumm" in out, "game sections untouched"
    assert device(run(tmp, out, both)) == ["mt32"], "idempotent"
    assert device(run(tmp, out, ("MT32_CONTROL.ROM",))) == ["null"], "one ROM is not enough"
    assert device(run(tmp, INI, ())) == ["null"], "no ROMs: no MT-32"
    owner = INI.replace("gfx_mode=opengl\n", "gfx_mode=opengl\nmt32_device=alsa_0\n")
    assert device(run(tmp, owner, both)) == ["alsa_0"], "owner's own device kept"

mk = (root / "projects/ROCKNIX/packages/emulators/standalone/scummvm-sa/package.mk").read_text()
assert "gm_device=" not in mk, "General MIDI games keep FluidSynth (owner 2026-11-19)"
for setting in ("music_driver=auto", "extrapath=/storage/roms/bios"):
    assert setting in mk, f"RK3128 default {setting}"
assert "mt32_device=mt32" not in mk, "the image never prefers MT-32 by itself"
print("mt32 seed: ok")
