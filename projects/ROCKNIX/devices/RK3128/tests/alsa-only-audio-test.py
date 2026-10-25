#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 image plays audio through ALSA dmix + softvol without PipeWire.

Test 39 (2026-10-11): a runtime prototype freed about 10 MB of RAM with the
frontend resident and left gameplay unchanged; ES sounds, Final Fight,
Olduvai and the volume keys worked. This checks the build-time wiring.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
rocknix = root / "projects/ROCKNIX"
device = rocknix / "devices/RK3128"


def read(path):
    return (root / path).read_text() if not isinstance(path, pathlib.Path) else path.read_text()


# PipeWire is off for the A12; its daemons and ALSA defaults follow the switch.
assert re.search(r'^\s*PIPEWIRE_SUPPORT="no"', read(device / "options"), re.M)
for pkg, units in (("pipewire", ("pipewire.socket", "pipewire-pulse.service")),
                   ("wireplumber", ("wireplumber.service",))):
    mk = read(rocknix / f"packages/audio/{pkg}/package.mk")
    block = re.search(r'if \[ "\$\{PIPEWIRE_SUPPORT\}" = "yes" \]; then\n(.*?)\n  fi', mk, re.S)
    assert block, f"{pkg}: services not gated on PIPEWIRE_SUPPORT"
    for unit in units:
        assert f"enable_service {unit}" in block[1], (pkg, unit)
        assert mk.count(f"enable_service {unit}") == 1, (pkg, unit)
pw = re.search(r'if \[ "\$\{PIPEWIRE_SUPPORT\}" = "yes" \]; then\n(.*?)\n  fi',
               read(rocknix / "packages/audio/pipewire/package.mk"), re.S)[1]
assert "99-pipewire-default.conf ${INSTALL}/etc/alsa/conf.d" in pw, "PipeWire must not own the ALSA default PCM"

# Startup must not start pipewire-pulse when it is not enabled.
audio = read(rocknix / "packages/rocknix/autostart/050-audio")
assert "systemctl is-enabled --quiet pipewire-pulse.service" in audio

# ES: SDL on ALSA, volume through the ALSA mixer when PipeWire is off.
dropin = read(device / "packages/quirks/system.d/emustation.service.d/20-a12-alsa.conf")
assert "Environment=SDL_AUDIODRIVER=alsa" in dropin
es = read(rocknix / "packages/ui/emulationstation/package.mk")
assert re.search(r'\[ "\$\{PIPEWIRE_SUPPORT\}" = "yes" \] && PKG_CMAKE_OPTS_TARGET\+=" -DENABLE_PULSE=1"', es)
assert "-DENABLE_PULSE=1 \\" not in es
assert 'export SDL_AUDIODRIVER="alsa"' in read(rocknix / "packages/hardware/quirks/platforms/RK3128/090-ui_service")
ra = read(rocknix / "packages/emulators/libretro/retroarch/sources/RK3128/retroarch.cfg")
assert re.search(r'^audio_driver = "alsa"$', ra, re.M)

# /etc/asound.conf: dmix at the codec's 48 kHz S32_LE, softvol "Master", default PCM.
conf = read(device / "packages/a12-controls/sources/asound.conf")
for needle in ("type dmix", 'pcm "hw:0,0"', "format S32_LE", "rate 48000",
               "type softvol", 'name "Master"', "pcm.!default", 'slave.pcm "a12_softvol"'):
    assert needle in conf, needle
assert 'asound.conf" "${INSTALL}/etc/asound.conf"' in read(device / "packages/a12-controls/package.mk")

# volume: pactl when a Pulse server answers, otherwise the ALSA "Master" control.
script = read(rocknix / "packages/rocknix/sources/scripts/volume")
for pulse_up, expect in ((True, "pactl -- set-sink-volume @DEFAULT_SINK@ 45%"),
                         (False, "amixer -q sset Master 45%")):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        log = tmp / "calls"
        (tmp / "functions").write_text(
            'get_setting() { echo 40; }\nset_setting() { echo "set_setting $*" >> "$LOG"; }\n')
        for tool, rc in (("pactl", 0 if pulse_up else 1), ("amixer", 0)):
            (tmp / tool).write_text(
                f'#!/bin/sh\n[ "$1" = info ] && exit {rc}\necho "{tool} $*" >> "$LOG"\n')
            (tmp / tool).chmod(0o755)
        body = script.replace("/etc/profile.d/001-functions", str(tmp / "functions"))
        subprocess.run(["bash", "-c", body, "volume", "up"], check=True,
                       env={"PATH": f"{tmp}:/usr/bin:/bin", "LOG": str(log)})
        calls = log.read_text()
        assert expect in calls and "set_setting audio.volume 45" in calls, calls
        assert ("amixer" in calls) != pulse_up, calls
# Existing installs: the A12 quirk moves RetroArch from pulse to alsa once,
# and leaves any other explicit choice alone.
quirk = read(rocknix / "packages/hardware/quirks/platforms/RK3128/025-alsa_audio")
for before, after in (('audio_driver = "pulse"', 'audio_driver = "alsa"'),
                      ('audio_driver = "null"', 'audio_driver = "null"')):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = pathlib.Path(tmp) / "retroarch.cfg"
        cfg.write_text(f'video_driver = "gl"\n{before}\naudio_enable = "true"\n')
        subprocess.run(["sh", "-c", quirk.replace("/storage/.config/retroarch/retroarch.cfg", str(cfg))], check=True)
        text = cfg.read_text()
        assert after in text and 'video_driver = "gl"' in text, text
print("alsa-only audio wiring: ok")
