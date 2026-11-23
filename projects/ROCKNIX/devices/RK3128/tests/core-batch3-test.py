#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Core batch 3 (owner, 2026-10-26): light systems KNULLI also runs.

atari800 (Atari 800/XL, and the 5200 alternative), a5200, fake08 (PICO-8),
tic80, o2em (Odyssey2/Videopac), arduous (Arduboy) and wasm4. All built for
the A12 unchanged and ran 1200 frames under QEMU with the image's
libraries, 10-16 MB peak memory each (test content: fake08's ld45 cart,
TIC-80's own fire/p3d demos, WASM-4 site carts, an open-source Arduboy
game, empty 5200/Odyssey2 carts on the owner's BIOS). The Atari and
Odyssey2 cores need the user's BIOS files in roms/bios. EasyRPG waits
(ICU and a dozen libraries for a 256 MB device); Potator builds with
platform=aarch64 only.
On the A12 itself (silent headless core-benchmark, CPU performance,
2026-10-26): fake08 ld45 11x; TIC-80 1.4x (p3d) to 10x; Atari 800 4.4x;
WASM-4 1.25x (antcopter) to 109x. Arduboy (arduous) ran 5 of 6 games at
0.43-0.47x: it simulates the 16 MHz AVR per instruction, which compiler
flags cannot double, so the A12 leaves it out (owner policy: the most
accurate core that runs). wasm4_libretro.so used powf/floorf/sqrtf
without linking libm (it only loaded because RetroArch links libm; the
harness under QEMU preloads libm, which hid it): the package links -lm.
PICO-8's default is the official (paid) PICO-8 binary, which no image
ships; with only built cores listed, fake08 must become its default.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
emulators = (root / "projects/ROCKNIX/packages/virtual/emulators/package.mk").read_text()
functions = (root / "distributions/ROCKNIX/config/functions").read_text()
a12 = re.search(r"^  RK3128\)\n(.*?)\n    ;;", emulators, re.M | re.S)[1]
cores = re.search(r'LIBRETRO_CORES="([^"]*)"', a12)[1].split()
batch = ("atari800-lr", "a5200-lr", "fake08-lr", "tic80-lr", "o2em-lr", "wasm4-lr")
for core in batch:
    assert core in cores, f"{core} not in the A12 core list"
assert "easyrpg-lr" not in cores and "potator-lr" not in cores
assert "arduous-lr" not in cores, "Arduboy runs at half speed on the A12"
wasm4 = (root / "projects/ROCKNIX/packages/emulators/libretro/wasm4-lr/package.mk").read_text()
assert '-DCMAKE_SHARED_LINKER_FLAGS="-lm"' in wasm4, "wasm4 must link libm itself"
built_wasm4 = root / "build.ROCKNIX-RK3128.arm/image/system/usr/lib/libretro/wasm4_libretro.so"
if built_wasm4.is_file():
    needed = subprocess.run(["readelf", "-d", str(built_wasm4)], capture_output=True, text=True).stdout
    assert "[libm.so.6]" in needed, "built wasm4 core does not link libm"


def func(name):
    return re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", functions, re.M | re.S)[0]


helpers = func("es_core_built") + func("es_emulator_built") + func("add_emu_core")


def listed(system, block_start, block_end, built):
    block = emulators.split(block_start)[1].split("\n", 1)[1].split(block_end)[0]
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


built = [c[:-3] for c in batch]
for system, head, default in (("atari800", "## Atari 800", "atari800"), ("atari5200", "### Atari 5200", "a5200"),
                              ("tic-80", "### Nesbox TIC-80", "tic80"), ("odyssey2", "### Magnavox Odyssey", "o2em"),
                              ("wasm4", "### Various WASM-4", "wasm4"),
                              ("pico-8", "### Lexaloffle PICO-8", "fake08")):
    got = listed(system, head, f"add_es_system {system}\n", built)
    assert f"retroarch|{default}|true" in got, (system, got)
print("core batch 3: ok")
