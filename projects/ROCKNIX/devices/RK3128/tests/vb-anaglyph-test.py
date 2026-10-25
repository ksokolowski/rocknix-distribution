#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""beetle_vb's A12 patches keep the picture bit-identical (tests 68-72).

0001 stages the Virtual Boy's column-by-column anaglyph output and writes it
row by row (NEON on ARM, a uniform and a general loop elsewhere), and skips
an eye drawn in black. 0002 skips idle XPSTTS polling loops in whole loop
periods. 0003 lets V810 loads and stores reach plain memory directly; 0004 makes the
idle check cheaper; 0005 skips fully transparent background rows. This builds the pinned beetle_vb natively twice, without and with
all patches, and compares core-benchmark frame hashes
(A12_BENCH_FRAMEHASH, Start+A pressed every 90 frames) over 3000 frames of
every .vb in A12_VB_ROMS, with ROCKNIX's 2D preset and with red & blue.
With arm-linux-gnueabihf-g++ and qemu-arm installed it repeats the
comparison with ARMv7 NEON builds under qemu-user, where the NEON output
paths run (the 2D preset takes the one-eye path, red & blue the two-eye one).
ROMs stay outside the repo: without A12_VB_ROMS the comparison is skipped and
only the patch is checked to apply to the pinned source.
"""
import concurrent.futures
import os
import pathlib
import re
import shutil
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = (root / "projects/ROCKNIX/packages/emulators/libretro/beetle-vb-lr/package.mk").read_text()
version = re.search(r'^PKG_VERSION="([0-9a-f]+)"', pkg, re.M)[1]
tarball = root / f"sources/beetle-vb-lr/beetle-vb-lr-{version}.tar.gz"
patches = sorted((root / "projects/ROCKNIX/devices/RK3128/patches/beetle-vb-lr").glob("*.patch"))
bench = root / "projects/ROCKNIX/devices/RK3128/tools/bench"
assert patches, "beetle-vb-lr patches missing"

if not tarball.exists():
    print("note: beetle-vb-lr source tarball not downloaded; anaglyph patch check skipped")
    raise SystemExit(0)


def unpack(dest, patched):
    with tarfile.open(tarball) as tar:
        for m in tar.getmembers():
            m.name = m.name.split("/", 1)[1] if "/" in m.name else ""
        tar.extractall(dest, members=[m for m in tar.getmembers() if m.name], filter="data")
    if patched:
        for p in patches:
            subprocess.run(["patch", "-p1", "-s", "-d", str(dest)], input=p.read_text(), text=True, check=True)


with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    unpack(tmp / "check", True)	# the patch applies to the pinned source
    roms_dir = os.environ.get("A12_VB_ROMS")
    if not roms_dir:
        print("vb anaglyph: patch applies (set A12_VB_ROMS=<dir of .vb> for the frame comparison)")
        raise SystemExit(0)
    roms = sorted(pathlib.Path(roms_dir).glob("*.vb"))
    assert roms, f"no .vb files in {roms_dir}"
    arm_flags = "-O2 -march=armv7ve -mtune=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard"
    cross, qemu = "arm-linux-gnueabihf-", shutil.which("qemu-arm-static") or shutil.which("qemu-arm")
    targets = [("native", [], {})]
    if shutil.which(cross + "g++") and qemu:
        # The Makefile appends to CFLAGS: pass them in the environment.
        targets.append(("arm", [qemu, "-L", f"/usr/{cross[:-1]}"],
                        dict(CC=cross + "gcc", CXX=cross + "g++", CFLAGS=arm_flags, CXXFLAGS=arm_flags)))
    else:
        print("note: arm-linux-gnueabihf-g++ or qemu-arm not installed; ARM (NEON) comparison skipped")
    (pathlib.Path("/tmp/a12-core-benchmark")).mkdir(exist_ok=True)

    def hashes(run, cb, core, rom, opt):
        env = dict(os.environ, A12_BENCH_FRAMEHASH="1", A12_BENCH_PRESS="90", A12_BENCH_WARMUP="0",
                   A12_BENCH_STAGES="5", A12_BENCH_OPT=opt)
        out = subprocess.run(run + [str(cb), str(core), str(rom)], env=env, capture_output=True, text=True, check=True).stdout
        return [l for l in out.splitlines() if l.startswith("hash ")]

    for target, run, make_env in targets:
        cores = {}
        for name, patched in (("orig", False), ("patched", True)):
            src = tmp / f"{target}-{name}"
            unpack(src, patched)
            subprocess.run(["make", f"-j{os.cpu_count()}", "platform=unix"], cwd=src, env=dict(os.environ, **make_env),
                           check=True, capture_output=True)
            cores[name] = src / "mednafen_vb_libretro.so"
        cb = tmp / f"core-benchmark-{target}"
        cc = [cross + "gcc"] + arm_flags.split() if run else ["gcc", "-O2"]
        subprocess.run(cc + ["-I", str(bench), "-o", str(cb), str(bench / "core-benchmark.c"), "-ldl", "-lm"], check=True)
        cases = [(rom, opt) for opt in ("", "vb_anaglyph_preset=red & blue") for rom in roms]
        with concurrent.futures.ThreadPoolExecutor(os.cpu_count()) as pool:
            jobs = {case: [pool.submit(hashes, run, cb, cores[n], *case) for n in ("orig", "patched")] for case in cases}
            for (rom, opt), (a, b) in jobs.items():
                a, b = a.result(), b.result()
                assert len(a) == 3000 and len({l.split()[2] for l in a}) > 100, (target, rom.name, len(a))
                diff = sum(x != y for x, y in zip(a, b))
                assert diff == 0, f"{target} {rom.name} [{opt or 'disabled'}]: {diff} of 3000 frames differ"
    print(f"vb anaglyph: ok ({'/'.join(t[0] for t in targets)}: {len(roms)} games x 2 presets x 3000 frames bit-identical)")
