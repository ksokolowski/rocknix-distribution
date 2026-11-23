#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-load-check starts each game in the core ES would (TEST_LOG test 64).

The core is the system's default from es_systems (image file plus the A12
test file), unless system.cfg names one for the game, as ES's per-game
options do (mame["pacman.zip"].core=fbneo: newer MAME romsets that MAME
2003-Plus cannot load). The ROM folder is the system's es_systems path
(colecovision lives in roms/coleco).
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
script = (root / "projects/ROCKNIX/devices/RK3128/tools/bench/a12-load-check").read_text()


def func(name):
    m = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", script, re.M | re.S)
    assert m, f"{name}() missing"
    return m[0]


with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    (tmp / "usr/config/emulationstation").mkdir(parents=True)
    (tmp / "storage/.config/emulationstation").mkdir(parents=True)
    (tmp / "storage/.config/system/configs").mkdir(parents=True)
    (tmp / "usr/config/emulationstation/es_systems.cfg").write_text(
        "<systemList><system><name>colecovision</name><path>/storage/roms/coleco</path></system>\n"
        "<system><name>mame</name><path>/storage/roms/mame</path><emulators><emulator name=\"retroarch\"><cores>\n"
        "<core default=\"true\">mame2003_plus</core>\n<core>fbneo</core>\n"
        "</cores></emulator></emulators></system></systemList>\n")
    (tmp / "storage/.config/emulationstation/es_systems_a12test.cfg").write_text(
        "<systemList><system>\n<name>c64</name>\n<core default=\"true\">vice_x64sc</core>\n</system></systemList>\n")
    (tmp / "storage/.config/system/configs/system.cfg").write_text(
        'mame["pacman.zip"].core=fbneo\nmame["pacman.zip"].emulator=retroarch\n'
        'snes["pacman.zip"].core=snes9x\n')

    def run(call):
        body = f"root={tmp}\nroms=/storage/roms\n" + func("default_core") + func("game_core") + func("system_dir") + func("verdict") + call + "\n"
        return subprocess.run(["bash", "-c", body], check=True, capture_output=True, text=True).stdout.strip()

    assert run("system_dir colecovision") == "/storage/roms/coleco"
    assert run("system_dir mame") == "/storage/roms/mame"
    assert run("system_dir nosuch") == "/storage/roms/nosuch"	# not listed: the name
    assert run("default_core mame") == "mame2003_plus"
    assert run("default_core c64") == "vice_x64sc", run("default_core c64")
    assert run("game_core mame pacman.zip") == "fbneo"
    assert run("game_core mame galaga.zip") == "mame2003_plus"
    # A12_LOAD_CORE forces one core for a comparison run (nestopia vs fceumm).
    assert run("A12_LOAD_CORE=nestopia game_core mame pacman.zip") == "nestopia"
    # The override is per system: the same file name elsewhere is not affected.
    assert run("game_core c64 pacman.zip") == "vice_x64sc"
# Verdicts read core-benchmark's stdout (speed lines) and stderr (core log)
# from files: dkongjr's MAME 2003-Plus run logged 185 MB of sound-CPU
# opcode errors, too much to pass as an argument (load-5 left it blank).
# SUSPECT = far above the system's rate *and* the core logging errors
# (Shark! Shark! .bin: 767 "Bad opcode" lines); light cores such as gw
# legitimately run at thousands of FPS without errors.
def verdict(rc, out, err=""):
    o = tmp_files / "out"; e = tmp_files / "err"
    o.write_text(out); e.write_text(err)
    return run(f"verdict {rc} {o} {e}")
import tempfile as _t
tmp_files = pathlib.Path(_t.mkdtemp())
fast = "frames 180-780 in 0.057 s = 10491.60 FPS; target 60.00 FPS\n"
assert verdict(0, "frames 180-780 in 3.0 s = 200.00 FPS; target 60.00 FPS\n") == "OK 200.00/60.00"
assert verdict(0, fast, "[ERROR][FREEINT] Bad opcode: 65535\n" * 20).startswith("SUSPECT")
assert verdict(0, fast).startswith("OK"), verdict(0, fast)	# gw: fast, no errors
# FreeIntv prints its errors to stdout (load-6: 767 lines there, none on stderr).
assert verdict(0, "[ERROR][FREEINT] Bad opcode: 65535\n" * 20 + fast).startswith("SUSPECT")
assert verdict(1, "", "load failed\n") == "LOAD-FAILED"
assert verdict(0, "", "I8039:  PC = 06b1,  opcode = 16\n" * 1000) == "FAIL rc=0"
assert verdict(124, "") == "TIMEOUT"
assert verdict(139, "") == "CRASH-SIG11"
# A relative OUT still works: logs are written after cd into the ROM folder
# (load-6: every game "crashed" with SIGPIPE because load-6/... did not
# exist there). End to end, with a fake core-benchmark.
import os
with tempfile.TemporaryDirectory() as t2:
    t2 = pathlib.Path(t2)
    (t2 / "usr/config/emulationstation").mkdir(parents=True)
    (t2 / "usr/config/emulationstation/es_systems.cfg").write_text(
        "<systemList><system>\n<name>nes</name>\n<path>%s/roms/nes</path>\n"
        "<core default=\"true\">fceumm</core>\n</system></systemList>\n" % t2)
    (t2 / "roms/nes").mkdir(parents=True)
    (t2 / "roms/nes/Game.nes").write_text("x")
    (t2 / "cores").mkdir()
    (t2 / "cores/fceumm_libretro.so").write_text("")
    (t2 / "cores/fceumm_libretro.info").write_text('supported_extensions = "nes"\n')
    bench = t2 / "core-benchmark"
    bench.write_text("#!/bin/sh\necho 'core log line' >&2\n"
                     "echo 'frames 180-780 in 3.0 s = 200.00 FPS; target 60.00 FPS'\n")
    bench.chmod(0o755)
    body = (script.replace("base=/storage/a12-coretest", f"base={t2}")
                  .replace("roms=/storage/roms", f"roms={t2}/roms")
                  .replace("cores=/tmp/cores", f"cores={t2}/cores")
                  .replace("systemctl", "true")
                  .replace("sysdir=/tmp/a12-core-benchmark", f"sysdir={t2}/sys")
                  .replace("work=/tmp/a12-load-check", f"work={t2}/work"))
    (t2 / "check").write_text(body)
    subprocess.run(["bash", str(t2 / "check"), "out", "nes"], cwd=t2, check=True,
                   env=dict(os.environ, A12_ROOT=str(t2)), capture_output=True)
    summary = (t2 / "out/summary.txt").read_text()
    assert "OK 200.00/60.00" in summary, summary
    assert "core log line" in (t2 / "out/nes-Game.log.err").read_text()
# The check keeps only the end of a core's log.
assert script.count("tail -c 1000000") == 2 and '"$log.err"' in script	# both streams capped
print("load check: ok")
