#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""B12 step 3: the KMS splash logo is rendered at build time.

rocknix-splash draws the ROCKNIX logo from built-in SVG paths on fbdev.
a12-controls links rocknix-splash's main.c and renderer into a build-host
tool (gen-logo) with the framebuffer, device checks and rotation wrapped,
and ships the result as /usr/share/a12-splash/logo.bmp. With
A12_ROCKNIX_SPLASH_SRC pointing at the pinned rocknix-splash source the
tool is built and its image checked; otherwise only the wiring is checked.
"""
import os
import pathlib
import re
import struct
import subprocess
import tempfile

device = pathlib.Path(__file__).resolve().parents[1]
mk = (device / "packages/a12-controls/package.mk").read_text()
splash = device / "packages/a12-controls/sources/splash"
main = (splash / "splash-main.c").read_text()

assert re.search(r'^PKG_DEPENDS_UNPACK="rocknix-splash( [^"]+)?"$', mk, re.M)
assert "--wrap=fb_init,--wrap=fb_flush,--wrap=fb_cleanup,--wrap=access,--wrap=get_display_rotation" in mk
assert '"${PKG_BUILD}/logo.bmp" "${INSTALL}/usr/share/a12-splash/logo.bmp"' in mk
assert '"/usr/share/a12-splash/logo.bmp"' in main

src = os.environ.get("A12_ROCKNIX_SPLASH_SRC")
if not src:
    print("note: A12_ROCKNIX_SPLASH_SRC not set; logo render skipped")
    print("splash logo: ok")
    raise SystemExit(0)

rs = pathlib.Path(src)
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    run = lambda *cmd: subprocess.run(cmd, cwd=tmp, check=True, capture_output=True)
    run("gcc", "-O2", "-c", "-Dmain=rocknix_splash_main", f"-I{rs}", str(rs / "main.c"), "-o", "rs-main.o")
    for name in ("fbsplash", "svg_parser", "svg_renderer"):
        run("gcc", "-O2", "-c", f"-I{rs}", str(rs / f"{name}.c"), "-o", f"rs-{name}.o")
    run("gcc", "-O2", "-Wall", "-Wextra", "-Werror", f"-I{rs}", f"-I{splash}", "-o", "gen-logo",
        str(splash / "gen-logo.c"), str(splash / "splash-draw.c"),
        "rs-main.o", "rs-fbsplash.o", "rs-svg_parser.o", "rs-svg_renderer.o",
        "-Wl,--wrap=fb_init,--wrap=fb_flush,--wrap=fb_cleanup,--wrap=access,--wrap=get_display_rotation", "-lm")
    run("./gen-logo", "logo.bmp")
    data = (tmp / "logo.bmp").read_bytes()

assert data[:2] == b"BM"
offset, width, height, bpp = struct.unpack_from("<I", data, 10)[0], *struct.unpack_from("<iiH", data, 18)[:2], struct.unpack_from("<H", data, 28)[0]
assert (width, height, bpp) == (1024, 600, 24), (width, height, bpp)
row = (width * 3 + 3) & ~3


def pixel(x, y):  # BMP rows are bottom-up, BGR
    b, g, r = data[offset + (height - 1 - y) * row + x * 3:][:3]
    return r, g, b


reds = [(x, y) for y in range(0, height, 2) for x in range(0, width, 2) if pixel(x, y) == (255, 85, 85)]
greys = [(x, y) for y in range(0, height, 2) for x in range(0, width, 2) if pixel(x, y) == (85, 85, 85)]
assert len(reds) > 1000 and len(greys) > 500, (len(reds), len(greys))
xs = [x for x, _ in reds + greys]
ys = [y for _, y in reds + greys]
assert abs((min(xs) + max(xs)) / 2 - width / 2) < 16 and abs((min(ys) + max(ys)) / 2 - height / 2) < 16
assert max(x for x, _ in reds) < min(x for x, _ in greys) + 30, "ROCK red left of NIX grey"
assert pixel(0, 0) == (0, 0, 0) and pixel(width - 1, height - 1) == (0, 0, 0)
print("splash logo: ok")
