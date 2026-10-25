#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-vop-dclk shows before writing, rejects bad modes and latches with CFG_DONE."""
import pathlib
import struct
import subprocess
import tempfile

source = pathlib.Path(__file__).resolve().parents[1] / "tools/bench/a12-vop-dclk.c"
with tempfile.TemporaryDirectory() as temporary:
    binary = pathlib.Path(temporary, "vop")
    subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-o", str(binary), str(source)], check=True)
    regs = pathlib.Path(temporary, "regs")
    data = bytearray(4096)
    struct.pack_into("<I", data, 0x2c, 1 << 25 | 1 << 24)
    regs.write_bytes(data)

    def run(*args):
        return subprocess.run([str(binary), *args, "--file", str(regs)], capture_output=True, text=True)

    shown = run("show")
    assert shown.returncode == 0 and "rgb_dclk_pol=1" in shown.stdout, shown
    assert run("bogus").returncode == 2
    assert struct.unpack_from("<I", regs.read_bytes(), 0x2c)[0] == 1 << 25 | 1 << 24, "bogus wrote"
    assert run("normal").returncode == 0
    raw = regs.read_bytes()
    assert struct.unpack_from("<I", raw, 0x2c)[0] == 1 << 24
    assert struct.unpack_from("<I", raw, 0x90)[0] == 1, "cfg_done not written"
print("vop dclk: ok")
