#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""ES lists only libretro cores the A12 image ships (ES_ONLY_BUILT_CORES).

The A12 builds 25 of the cores that es_systems names; NES and SNES defaulted
to nestopia and snes9x, which are not in the image (core survey 2026-10-11).
With ES_ONLY_BUILT_CORES=yes, add_emu_core drops RetroArch cores that no
package installed, and a dropped default passes to the next listed core
that exists. The core lists run roughly from most to least accurate, so this
keeps the owner's policy: the most accurate core that runs.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
functions = (root / "distributions/ROCKNIX/config/functions").read_text()
emulators = (root / "projects/ROCKNIX/packages/virtual/emulators/package.mk").read_text()
func = re.search(r"^add_emu_core\(\) \{\n.*?^\}\n", functions, re.M | re.S)[0]
helper = re.search(r"^es_core_built\(\) \{\n.*?^\}\n", functions, re.M | re.S)
emu_helper = re.search(r"^es_emulator_built\(\) \{\n.*?^\}\n", functions, re.M | re.S)
sysdoc = re.search(r"^add_system_doc\(\) \{\n.*?^\}\n", functions, re.M | re.S)[0]
sysdir = re.search(r"^add_system_dir\(\) \{\n.*?^\}\n", functions, re.M | re.S)[0]
essystem = re.search(r"^add_es_system\(\) \{\n.*?^\}\n", functions, re.M | re.S)[0]
assert helper, "es_core_built() missing"
assert emu_helper, "es_emulator_built() missing"
helpers = helper[0] + emu_helper[0]

# The A12 case in the emulators package turns the filter on.
a12 = re.search(r"^  RK3128\)\n(.*?)\n    ;;", emulators, re.M | re.S)[1]
assert 'ES_ONLY_BUILT_CORES="yes"' in a12, a12

# GBA's gpsp and PS1's pcsx_rearmed are listed per device; the A12 ships both.
gba = re.search(r"add_emu_core gba retroarch skyemu false\n  case \$\{DEVICE\} in\n    ([^)]*)\)", emulators)[1]
assert "RK3128" in gba.split("|"), gba
psx = re.search(r"### Sony Playstation\n  case \$\{DEVICE\} in\n    ([^)]*)\)", emulators)[1]
assert "RK3128" in psx.split("|"), psx


def install(tmp, built, scripts=(), commands=()):
    for core in built:
        lib = tmp / f"build/install_pkg/{core}-lr-1/usr/lib/libretro"
        lib.mkdir(parents=True, exist_ok=True)
        (lib / f"{core}_libretro.so").write_text("")
    for name in scripts:
        bindir = tmp / f"build/install_pkg/{name}-1/usr/bin"
        bindir.mkdir(parents=True, exist_ok=True)
        (bindir / f"start_{name}.sh").write_text("")
    conf = tmp / "root/config/emulators"
    conf.mkdir(parents=True, exist_ok=True)
    for system in commands:
        (conf / f"{system}.conf").write_text(f'SYSTEM_NAME="{system}"\nSYSTEM_COMMAND="/bin/sh %ROM%"\n')


def run(calls, built, only="yes", scripts=(), commands=(), image=None, stale=()):
    """built: cores whose package is in the image's LIBRETRO_CORES (image,
    default all of built); stale: cores left in the build tree by packages
    the image does not include."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        install(tmp, list(built) + list(stale), scripts, commands)
        pkgs = " ".join(f"{c}-lr" for c in (built if image is None else image))
        script = (f"ESTMP={tmp}/es\nBUILD={tmp}/build\nROOT={tmp}/root\nES_ONLY_BUILT_CORES={only}\n"
                  f"LIBRETRO_CORES=\"{pkgs}\"\n"
                  "add_emu_doc() { :; }\n" + helpers + func +
                  "\n".join(f"add_emu_core {c}" for c in calls) + "\n")
        subprocess.run(["bash", "-c", script], check=True)
        out = {}
        for f in sorted((tmp / "es").glob("*-emulators.tmp")):
            out[f.name.split("-emulators")[0]] = f.read_text().split()
        return out


nes = ["nes retroarch nestopia true", "nes retroarch fceumm false",
       "nes retroarch quicknes false", "nes retroarch mesen false"]
assert run(nes, ["fceumm", "quicknes"]) == {
    "nes": ["retroarch|fceumm|true", "retroarch|quicknes|false"]}
# A core another package left in the build tree is not in the image
# (PUAE 2021 from a comparison build, sync5 2026-10-17): dropped.
assert run(["amiga retroarch puae2021 true", "amiga retroarch uae4arm false"],
           ["uae4arm"], stale=["puae2021"]) == {"amiga": ["retroarch|uae4arm|true"]}
# Default present: unchanged apart from dropping missing cores.
assert run(["gba retroarch mgba true", "gba retroarch vbam false", "gba retroarch gpsp false"],
           ["mgba", "gpsp"]) == {"gba": ["retroarch|mgba|true", "retroarch|gpsp|false"]}
# Standalone emulators are kept when a package installed start_<core>.sh,
# which is what runemu.sh runs for them.
assert run(["scummvm scummvm scummvm-sa true"], [], scripts=["scummvm"]) == \
    {"scummvm": ["scummvm|scummvm-sa|true"]}
assert run(["psx duckstation duckstation-sa false", "psx retroarch pcsx_rearmed true"],
           ["pcsx_rearmed"]) == {"psx": ["retroarch|pcsx_rearmed|true"]}
assert run(["n64 mupen64plus mupen64plus-sa true", "n64 retroarch mupen64plus false"], []) == {}
assert run(["pcfx mednafen pcfx true"], [], scripts=["mednafen"]) == {"pcfx": ["mednafen|pcfx|true"]}
# Platforms runemu.sh dispatches itself and systems with their own command
# have no start_<core>.sh to look for: never filtered.
assert run(["gamecube dolphin dolphin-sa-gc true"], []) == {"gamecube": ["dolphin|dolphin-sa-gc|true"]}
assert run(["moonlight moonlight moonlight true"], [], commands=["moonlight"]) == \
    {"moonlight": ["moonlight|moonlight|true"]}
# Other devices: filter off, upstream behaviour.
assert run(nes, [], only="") == {"nes": ["retroarch|nestopia|true", "retroarch|fceumm|false",
                                         "retroarch|quicknes|false", "retroarch|mesen|false"]}
# A system whose only core is dropped still gets its documentation row
# (add_emu_doc used to be what created the doc directory).
with tempfile.TemporaryDirectory() as tmp:
    script = (f"ESTMP={tmp}/es\nDOCTMP={tmp}/doc\nBUILD={tmp}/build\nES_ONLY_BUILT_CORES=yes\n"
              "add_emu_doc() { :; }\n" + helpers + func + sysdoc +
              "add_emu_core bbcmicro retroarch b2 true\nSYSTEM_NAME=bbcmicro SYSTEM_PATH=/x\nadd_system_doc bbcmicro\n")
    subprocess.run(["bash", "-e", "-c", script], check=True)
    assert (pathlib.Path(tmp) / "doc/bbcmicro:system.tmp").exists()
# A system whose emulators were all dropped is left out of es_systems (its
# games could not start) but keeps its ROM directory and documentation.
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    install(tmp, [])
    script = (f"ESTMP={tmp}/es\nDOCTMP={tmp}/doc\nBUILD={tmp}/build\nROOT={tmp}/root\n"
              "ES_ONLY_BUILT_CORES=yes\nadd_emu_doc() { :; }\n" + helpers + func + sysdoc + sysdir + essystem +
              "add_emu_core n64 mupen64plus mupen64plus-sa true\nadd_emu_core n64 retroarch parallel_n64 false\n"
              "SYSTEM_NAME=n64 SYSTEM_PATH=/storage/roms/n64\nadd_es_system n64\n")
    subprocess.run(["bash", "-e", "-c", script], check=True)
    assert not (tmp / "es/n64.tmp").exists(), "a system with no emulator must not reach es_systems"
    assert "/storage/roms/n64" in (tmp / "es/system-dirs.conf").read_text()
    assert (tmp / "doc/n64:system.tmp").exists()
# On a built image: every RetroArch core es_systems names is in the image.
image = root / "build.ROCKNIX-RK3128.arm/image/system"
es_cfg = image / "usr/config/emulationstation/es_systems.cfg"
if es_cfg.exists():
    shipped = {p.name[:-len("_libretro.so")] for p in (image / "usr/lib/libretro").glob("*_libretro.so")}
    listed = set()
    for system in re.findall(r"<system>(.*?)</system>", es_cfg.read_text(), re.S):
        for emulator in re.findall(r'<emulator name="retroarch">(.*?)</emulator>', system, re.S):
            listed |= set(re.findall(r"<core[^>]*>([^<]+)</core>", emulator))
    assert listed <= shipped, f"es_systems names cores the image lacks: {sorted(listed - shipped)}"
print("es built cores: ok")
