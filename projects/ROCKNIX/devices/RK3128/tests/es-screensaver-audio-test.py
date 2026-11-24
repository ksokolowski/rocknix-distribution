#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""ES closes audio while its screensaver runs on the A12 (2026-10-28).

With the screen dark ES kept its SDL audio stream open and played silence:
the speaker amplifier (spk-ctl) stayed on, I2S ran at 12.288 MHz and the
PL330 interrupted 47 times a second. ES already closes audio when the
screensaver starts and reopens it when it stops, behind
StopMusicOnScreenSaver, which defaults to false. A12 ES patch 0005 makes it
true on RK3128 in Settings.cpp, so existing installs get it too (ES saves
only values that differ from the default). The patches must apply to the
pinned ES source in order; that part runs when the tarball is in sources/.
"""
import pathlib
import re
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
patches = root / "projects/ROCKNIX/devices/RK3128/patches/emulationstation"
patch = patches / "0005-screensaver-close-audio-on-rk3128.patch"
assert patch.is_file(), patch
text = patch.read_text()
assert "#if defined(RK3128)" in text
assert 'mBoolMap["StopMusicOnScreenSaver"] = true;' in text

version = re.search(r'^PKG_VERSION="([0-9a-f]+)"',
                    (root / "projects/ROCKNIX/packages/ui/emulationstation/package.mk").read_text(), re.M)[1]
tarball = root / f"sources/emulationstation/emulationstation-{version}.tar.gz"
if not tarball.is_file():
    print("es screensaver audio: ok (SKIP apply: ES source not downloaded)")
    raise SystemExit(0)
with tempfile.TemporaryDirectory() as tmp:
    with tarfile.open(tarball) as t:
        t.extractall(tmp, filter="data")
    src = next(pathlib.Path(tmp).iterdir())
    for p in sorted(patches.glob("*.patch")):
        r = subprocess.run(["patch", "-p1", "--forward", "-i", str(p)], cwd=src, capture_output=True, text=True)
        assert r.returncode == 0, f"{p.name} does not apply:\n{r.stdout}{r.stderr}"
    settings = (src / "es-core/src/Settings.cpp").read_text()
    block = re.search(r'#if defined\(RK3128\)\n(.*?)\n#else\n(.*?)\n#endif', settings, re.S)
    assert block, "RK3128 block around the default"
    assert 'mBoolMap["StopMusicOnScreenSaver"] = true;' in block[1]
    assert 'mBoolMap["StopMusicOnScreenSaver"] = false;' in block[2], "other devices keep the upstream default"
    saver = (src / "es-app/src/SystemScreenSaver.cpp").read_text()
    start = saver[saver.index("void SystemScreenSaver::startScreenSaver()"):]
    stop = saver[saver.index("void SystemScreenSaver::stopScreenSaver()"):]
    assert re.search(r'getBool\("StopMusicOnScreenSaver"\)\)[^\n]*\n\s*AudioManager::getInstance\(\)->deinit\(\);', start)
    assert re.search(r'getBool\("StopMusicOnScreenSaver"\)\)[^\n]*\n\s*\{\s*AudioManager::getInstance\(\)->init\(\);', stop)
print("es screensaver audio: ok")
