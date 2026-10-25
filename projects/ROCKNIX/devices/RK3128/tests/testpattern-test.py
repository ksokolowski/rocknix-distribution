#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-testpattern draws bars, a grey ramp and a 1-pixel checkerboard (XRGB8888)."""
import pathlib
import struct
import subprocess
import tempfile

source = pathlib.Path(__file__).resolve().parents[1] / "tools/bench/a12-testpattern.c"
width, height = 64, 30
with tempfile.TemporaryDirectory() as temporary:
    binary = pathlib.Path(temporary, "pattern")
    subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-o", str(binary), str(source)], check=True)
    raw = pathlib.Path(temporary, "frame.raw")
    subprocess.run([str(binary), "--raw", str(width), str(height), str(raw)], check=True)
    data = raw.read_bytes()

assert len(data) == width * height * 4, len(data)


def pixel(x, y):
    return struct.unpack_from("<I", data, (y * width + x) * 4)[0] & 0xffffff


# Bars: 8 columns across the top third, white first and black last.
assert pixel(0, 0) == 0xffffff
assert pixel(width // 8 + 1, 0) == 0xffff00, hex(pixel(width // 8 + 1, 0))   # yellow
assert pixel(width - 1, 0) == 0x000000
# Ramp: middle third, grey from 0 to 255.
assert pixel(0, height // 2) == 0x000000
assert pixel(width - 1, height // 2) == 0xffffff
middle = pixel(width // 2, height // 2)
assert middle & 0xff == (middle >> 8) & 0xff == (middle >> 16) & 0xff, hex(middle)
# Checkerboard: bottom third alternates every pixel.
y = height - 1
assert pixel(0, y) != pixel(1, y) and pixel(0, y) == pixel(1, y - 1)
print("testpattern: ok")
