#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Core batch 2 (owner, 2026-10-17: prefer the most accurate core that runs).

The A12 ships nestopia (NES and FDS default: more accurate than fceumm, at
least 1.9x headroom), prosystem, vecx, beetle_wswan, beetle_vb and uae4arm
(Amiga default: PUAE 2021 ran at 0.54x). uae4arm builds for the A12's CPU:

ROCKNIX's uae4arm package always passed platform=unix_aarch64, whose
inline assembly does not build for 32-bit ARM. The A12 (Cortex-A7,
NEON-VFPv4, hard float) uses the core's classic_armv7_a7 target; other
devices keep unix_aarch64. That target does not link the libraries the
core needs (zlib, FLAC, Ogg, mpg123), so the A12 adds them to its block.
"""
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
pkg = root / "projects/ROCKNIX/packages/emulators/libretro/uae4arm-lr/package.mk"


def opts(device, arch):
    return subprocess.run(["bash", "-c", f'DEVICE={device}; ARCH={arch}; . "{pkg}"; echo "$PKG_MAKE_OPTS_TARGET"'],
                          check=True, capture_output=True, text=True).stdout.split()


assert "platform=classic_armv7_a7" in opts("RK3128", "arm"), opts("RK3128", "arm")
assert "platform=unix_aarch64" in opts("RK3326", "aarch64"), opts("RK3326", "aarch64")
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    mk = pathlib.Path(tmp) / "Makefile.libretro"
    mk.write_text("ifeq ($(platform), unix_aarch64)\n\tLDFLAGS += -lz -lpthread -lFLAC -lmpg123 -ldl\n"
                  "else ifeq ($(platform), classic_armv7_a7)\n\tHAVE_NEON = 1\n"
                  "else ifeq ($(platform), classic_armv8_a35)\n\tHAVE_NEON = 1\nendif\n")
    for device in ("RK3128", "RK3326"):
        text = mk.read_text()
        subprocess.run(["bash", "-c", f'DEVICE={device}; PKG_BUILD={tmp}; . "{pkg}"; post_unpack'], check=True)
        block = mk.read_text().split("classic_armv7_a7)")[1].split("else ifeq")[0]
        if device == "RK3128":
            assert "-lz" in block and "-lmpg123" in block and "-lFLAC -logg" in block, block
        else:
            assert "-lz" not in block, block
        mk.write_text(text)
import re
emulators = (root / "projects/ROCKNIX/packages/virtual/emulators/package.mk").read_text()
functions = (root / "distributions/ROCKNIX/config/functions").read_text()
a12 = re.search(r"^  RK3128\)\n(.*?)\n    ;;", emulators, re.M | re.S)[1]
cores = re.search(r'LIBRETRO_CORES="([^"]*)"', a12)[1].split()
for core in ("nestopia-lr", "prosystem-lr", "vecx-lr", "beetle-wswan-lr", "beetle-vb-lr", "uae4arm-lr"):
    assert core in cores, f"{core} not in the A12 core list"
assert "puae2021-lr" not in cores and "puae-lr" not in cores


def func(name):
    return re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", functions, re.M | re.S)[0]


helpers = func("es_core_built") + func("es_emulator_built") + func("add_emu_core")


def listed(system, block_start, block_end, built):
    block = emulators.split(block_start)[1].split(block_end)[0]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        for core in built:
            lib = tmp / f"build/install_pkg/{core}-1/usr/lib/libretro"
            lib.mkdir(parents=True, exist_ok=True)
            (lib / f"{core}_libretro.so").write_text("")
        script = (f"ESTMP={tmp}/es\nBUILD={tmp}/build\nROOT={tmp}\nDEVICE=RK3128\nES_ONLY_BUILT_CORES=yes\n"
                  f"LIBRETRO_CORES=\"{' '.join(built)}\"\n"
                  "add_emu_doc() { :; }\n" + helpers + block)
        subprocess.run(["bash", "-e", "-c", script], check=True)
        f = tmp / f"es/{system}-emulators.tmp"
        return f.read_text().split() if f.exists() else []


assert listed("amiga", "### Commodore Amiga\n", "add_es_system amiga", ["uae4arm"]) == \
    ["retroarch|uae4arm|true"], listed("amiga", "### Commodore Amiga\n", "add_es_system amiga", ["uae4arm"])
built = ["nestopia", "fceumm", "quicknes"]
for system, head in (("nes", "  ### Nintendo NES\n"), ("fds", "  ### Nintendo Famicom Disk System\n")):
    got = listed(system, head, f"add_es_system {system}\n", built)
    assert got == ["retroarch|nestopia|true", "retroarch|fceumm|false", "retroarch|quicknes|false"], (system, got)
print("core batch 2: ok")
