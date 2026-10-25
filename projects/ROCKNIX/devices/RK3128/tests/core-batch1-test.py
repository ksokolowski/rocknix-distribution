#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Core batch 1 (TEST_LOG test 64): Game & Watch, MSX, C64 and DOS on the A12.

The A12 ships gw, bluemsx, dosbox_pure and VICE. C64 defaults to the
cycle-exact x64sc (owner policy: the most accurate core that runs) with the
fast x64 as the fallback; VICE builds only those two on the A12 instead of
ten machines. blueMSX needs its Machines/Databases tree in the BIOS
directory: the A12 image carries the core's machine configs, databases and
free C-BIOS ROMs (no proprietary BIOS dumps) and a boot hook seeds them when
missing, never overwriting what the owner put there.
Other devices keep upstream behaviour.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
rk = root / "projects/ROCKNIX/devices/RK3128"
emulators = (root / "projects/ROCKNIX/packages/virtual/emulators/package.mk").read_text()
functions = (root / "distributions/ROCKNIX/config/functions").read_text()
libretro = root / "projects/ROCKNIX/packages/emulators/libretro"


def func(text, name):
    m = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.M | re.S)
    assert m, f"{name}() missing"
    return m[0]


# The A12 core list carries the batch.
a12 = re.search(r"^  RK3128\)\n(.*?)\n    ;;", emulators, re.M | re.S)[1]
cores = re.search(r'LIBRETRO_CORES="([^"]*)"', a12)[1].split()
for core in ("gw-lr", "bluemsx-lr", "dosbox-pure-lr", "vice-lr"):
    assert core in cores, f"{core} not in the A12 core list"

# C64: x64sc is the A12 default, x64 the fallback; upstream order elsewhere.
block = re.search(r"  ### Commodore 64\n(.*?)  add_es_system c64\n", emulators, re.S)[1]
helpers = func(functions, "es_core_built") + func(functions, "es_emulator_built") + func(functions, "add_emu_core")


def c64(device, built, only):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        for core in built:
            lib = tmp / f"build/install_pkg/{core}-1/usr/lib/libretro"
            lib.mkdir(parents=True, exist_ok=True)
            (lib / f"{core}_libretro.so").write_text("")
        script = (f"ESTMP={tmp}/es\nBUILD={tmp}/build\nROOT={tmp}\nDEVICE={device}\n"
                  f"LIBRETRO_CORES=\"{' '.join(built)}\"\n"
                  f"ES_ONLY_BUILT_CORES={only}\nadd_emu_doc() {{ :; }}\n" + helpers + block)
        subprocess.run(["bash", "-e", "-c", script], check=True)
        return (tmp / "es/c64-emulators.tmp").read_text().split()


assert c64("RK3128", ["vice_x64sc", "vice_x64"], "yes") == \
    ["retroarch|vice_x64sc|true", "retroarch|vice_x64|false"], c64("RK3128", ["vice_x64sc", "vice_x64"], "yes")
assert c64("RK3326", [], "") == ["retroarch|vice_x64|true", "vicesa|x64sc|false"], c64("RK3326", [], "")

# VICE: the A12 builds and installs x64sc and x64 only.
vice = (libretro / "vice-lr/package.mk").read_text()


def vice_build(device):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "src").mkdir()
        script = (f"DEVICE={device}\nINSTALL={tmp}/inst\ncd {tmp}/src\n"
                  "make() { case \"$1\" in clean) ;; EMUTYPE=*) touch vice_${1#EMUTYPE=}_libretro.so; echo ${1#EMUTYPE=} >> ../made ;; esac; }\n"
                  + func(vice, "make_target") + func(vice, "makeinstall_target")
                  + "make_target\nmakeinstall_target\n")
        subprocess.run(["bash", "-e", "-c", script], check=True)
        made = (tmp / "made").read_text().split()
        inst = sorted(p.name for p in (tmp / "inst/usr/lib/libretro").iterdir())
        return made, inst


made, inst = vice_build("RK3128")
assert sorted(made) == ["x64", "x64sc"], made
assert inst == ["vice_x64_libretro.so", "vice_x64sc_libretro.so"], inst
made, inst = vice_build("RK3326")
assert len(made) == 10 and "vice_x64sc_libretro.so" not in inst, (made, inst)

# blueMSX: the A12 image carries Machines/Databases in /usr/share/bluemsx.
bluemsx = (libretro / "bluemsx-lr/package.mk").read_text()


def bluemsx_install(device):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        src = tmp / "src"
        for d in ("system/bluemsx/Machines/MSX - C-BIOS", "system/bluemsx/Machines/COL - ColecoVision",
                  "system/bluemsx/Machines/Shared Roms", "system/bluemsx/Databases"):
            (src / d).mkdir(parents=True)
        (src / "system/bluemsx/Machines/MSX - C-BIOS/cbios_main_msx1.rom").write_text("x")
        (src / "system/bluemsx/Machines/MSX - C-BIOS/config.ini").write_text("x")
        (src / "system/bluemsx/Machines/COL - ColecoVision/config.ini").write_text("x")
        (src / "system/bluemsx/Machines/COL - ColecoVision/coleco.rom").write_text("x")
        (src / "system/bluemsx/Machines/Shared Roms/MSX.rom").write_text("x")
        (src / "system/bluemsx/Machines/Shared Roms/MSXDOS23.ROM").write_text("x")
        (src / "system/bluemsx/Databases/msxromdb.xml").write_text("x")
        (src / "bluemsx_libretro.so").write_text("")
        script = (f"DEVICE={device}\nINSTALL={tmp}/inst\ncd {src}\n"
                  + func(bluemsx, "makeinstall_target") + "makeinstall_target\n")
        subprocess.run(["bash", "-e", "-c", script], check=True)
        return sorted(str(p.relative_to(tmp / "inst")) for p in (tmp / "inst").rglob("*") if p.is_file())


files = bluemsx_install("RK3128")
assert "usr/share/bluemsx/Machines/MSX - C-BIOS/cbios_main_msx1.rom" in files, files
assert "usr/share/bluemsx/Databases/msxromdb.xml" in files, files
# Machine configs ship, BIOS dumps do not: only the free C-BIOS ROMs go into
# the image (the core falls back to C-BIOS for cartridges).
assert "usr/share/bluemsx/Machines/COL - ColecoVision/config.ini" in files, files
assert not [f for f in files if f.lower().endswith(".rom") and "/cbios_" not in f], files
assert bluemsx_install("RK3326") == ["usr/lib/libretro/bluemsx_libretro.so"]

# Boot hook: seed the BIOS directory once, keep the owner's files.
hook = rk / "packages/a12-controls/sources/022-a12-bios"
assert hook.exists(), "022-a12-bios missing"
pkg = (rk / "packages/a12-controls/package.mk").read_text()
# It writes to /storage/roms, so it runs in the device stage, after automount.
assert '"${INSTALL}/usr/lib/autostart/RK3128/"' in pkg and "autostart/common/022-a12-bios" not in pkg, \
    "022-a12-bios must be installed to /usr/lib/autostart/RK3128"
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    share = tmp / "usr/share/bluemsx"
    (share / "Machines/MSX").mkdir(parents=True)
    (share / "Machines/MSX/config.ini").write_text("image")
    (share / "Databases").mkdir()
    (share / "Databases/msxromdb.xml").write_text("image")
    bios = tmp / "storage/roms/bios"
    bios.mkdir(parents=True)
    env = {"A12_ROOT": str(tmp), "PATH": "/usr/bin:/bin"}
    subprocess.run(["bash", str(hook)], check=True, env=env)
    assert (bios / "Machines/MSX/config.ini").read_text() == "image"
    assert (bios / "Databases/msxromdb.xml").read_text() == "image"
    # The owner's copy stays as it is.
    (bios / "Machines/MSX/config.ini").write_text("owner")
    (share / "Machines/MSX/config.ini").write_text("image2")
    subprocess.run(["bash", str(hook)], check=True, env=env)
    assert (bios / "Machines/MSX/config.ini").read_text() == "owner"
    # No image copy (other builds): nothing to do, no error.
    subprocess.run(["bash", str(hook)], check=True, env={"A12_ROOT": str(tmp / "none"), "PATH": "/usr/bin:/bin"})
print("core batch 1: ok")
