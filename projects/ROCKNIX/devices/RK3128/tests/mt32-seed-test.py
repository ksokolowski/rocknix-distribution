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
    # mt32_device=mt32 only helps if ScummVM looks in the BIOS folder: a card
    # set up before the A12 defaults had no extrapath, and MT-32 games went
    # silent (the A13, test 102). Added once; the owner's own path stays.
    extra = lambda text: [l for l in text.split("\n[", 1)[0].splitlines() if l.startswith("extrapath=")]
    assert extra(run(tmp, INI, both)) == ["extrapath=/storage/roms/bios"], "BIOS folder for the ROMs"
    assert extra(run(tmp, INI.replace("music_driver=auto\n", "music_driver=auto\nextrapath=/media/x\n"), both)) == \
        ["extrapath=/media/x"], "owner's own extrapath kept"
    owner = INI.replace("gfx_mode=opengl\n", "gfx_mode=opengl\nmt32_device=alsa_0\n")
    assert device(run(tmp, owner, both)) == ["alsa_0"], "owner's own device kept"

    # 48 kHz like the A12's dmix reaches cards configured before it (test 93):
    # added once, a rate the owner set is kept.
    rate = lambda text: [l for l in text.split("\n[", 1)[0].splitlines() if l.startswith("output_rate=")]
    out = run(tmp, INI, ())
    assert rate(out) == ["output_rate=48000"], out
    assert rate(run(tmp, out, ())) == ["output_rate=48000"], "idempotent"
    assert rate(run(tmp, INI.replace("gfx_mode=opengl\n", "gfx_mode=opengl\noutput_rate=22050\n"), ())) == \
        ["output_rate=22050"], "owner's own rate kept"

# HQ3x for 320-wide games (owner 2026-11-24): a card still on the earlier A12
# default (OpenGL, no scaler) switches once; ScummVM lowers the factor for
# wider games by itself. Anything the owner set, then or later, stays.
def head(text):
    return text.split("\n[", 1)[0].splitlines()


def gfx(text):
    return [l for l in head(text) if l.split("=", 1)[0] in ("gfx_mode", "scaler", "scale_factor")]


with tempfile.TemporaryDirectory() as tmp:
    out = run(tmp, INI, ())
    assert sorted(gfx(out)) == ["gfx_mode=surfacesdl", "scale_factor=3", "scaler=xbrf"], out
    assert "[atlantis]\nengineid=scumm" in out, "game sections untouched"
    back = out.replace("gfx_mode=surfacesdl\n", "gfx_mode=opengl\n").replace("scaler=xbrf\n", "").replace("scale_factor=3\n", "")
    assert sorted(gfx(run(tmp, back, ()))) == ["gfx_mode=opengl"], "switched once: going back to OpenGL stays"
with tempfile.TemporaryDirectory() as tmp:
    own = INI.replace("gfx_mode=opengl\n", "gfx_mode=opengl\nscaler=normal\n")
    assert sorted(gfx(run(tmp, own, ()))) == ["gfx_mode=opengl", "scaler=normal"], "an owner's scaler is kept"
# xBRF replaces the HQ3x default (owner 2026-11-24): a card on HQ3x 3x
# switches once; HQ chosen again later, or another scaler, stays.
with tempfile.TemporaryDirectory() as tmp:
    hq = INI.replace("gfx_mode=opengl\n", "gfx_mode=surfacesdl\nscaler=hq\nscale_factor=3\n")
    out = run(tmp, hq, ())
    assert sorted(gfx(out)) == ["gfx_mode=surfacesdl", "scale_factor=3", "scaler=xbrf"], out
    assert sorted(gfx(run(tmp, hq, ()))) == ["gfx_mode=surfacesdl", "scale_factor=3", "scaler=hq"], "once: HQ again stays"
with tempfile.TemporaryDirectory() as tmp:
    own = INI.replace("gfx_mode=opengl\n", "gfx_mode=surfacesdl\nscaler=advmame\nscale_factor=3\n")
    assert sorted(gfx(run(tmp, own, ()))) == ["gfx_mode=surfacesdl", "scale_factor=3", "scaler=advmame"], "own scaler kept"
# A card from before the A12's OpenGL default (the public October release,
# the A13: test 101) has the shipped software renderer and no scaler.
with tempfile.TemporaryDirectory() as tmp:
    plain = INI.replace("gfx_mode=opengl\n", "gfx_mode=surfacesdl\n")
    assert sorted(gfx(run(tmp, plain, ()))) == ["gfx_mode=surfacesdl", "scale_factor=3", "scaler=xbrf"], \
        "no scaler chosen: xBRF"
    assert sorted(gfx(run(tmp, plain, ()))) == ["gfx_mode=surfacesdl"], "once"

mk = (root / "projects/ROCKNIX/packages/emulators/standalone/scummvm-sa/package.mk").read_text()
assert "gm_device=" not in mk, "General MIDI games keep FluidSynth (owner 2026-11-19)"
for setting in ("music_driver=auto", "extrapath=/storage/roms/bios"):
    assert setting in mk, f"RK3128 default {setting}"
assert "mt32_device=mt32" not in mk, "the image never prefers MT-32 by itself"
print("mt32 seed: ok")
