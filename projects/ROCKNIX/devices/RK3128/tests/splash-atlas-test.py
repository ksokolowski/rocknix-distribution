#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The initramfs status line looks like the boot splash's (test 61).

a12-splash draws its status line with FreeType from ES's font; the initramfs
has neither, so a12-update-splash used the scaled 8x16 bitmap font. gen-glyphs
renders ES's font at build time into a glyph table (splash-glyphs.h) and
splash-atlas.c draws from it. Render the same lines through FreeType
(splash-ttf.c) and through the table: the frames must be identical.
"""
import glob
import os
import pathlib
import shutil
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
splash = root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/sources/splash"
fonts = sorted(glob.glob(str(root / "build.*/build/emulationstation-*/resources/opensans_hebrew_condensed_regular.ttf")))
ft = subprocess.run(["pkg-config", "--cflags", "--libs", "freetype2"], capture_output=True, text=True)
if not fonts or ft.returncode or not shutil.which("cc"):
    print("SKIP splash-atlas-test (needs ES's font from a build and host FreeType)")
    raise SystemExit(0)
font, ftflags = fonts[0], ft.stdout.split()

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "splash-draw.h"
int main(int argc, char **argv)
{
	static uint32_t px[1024 * 600];
	struct splash_frame f = { px, 1024, 600, 1024 };
	struct splash_layout l;
	splash_layout_for(1024, 600, &l);
	for (int i = 1; i < argc; i++) {
		memset(px, 0, sizeof(px));
		splash_text(&f, &l, argv[i]);
		fwrite(px + l.text_y * 1024, 4, (size_t)l.text_h * 1024, stdout);
	}
	return 0;
}
'''
LINES = ["Updating System...", "Checking disk(s): /dev/mmcblk0p2", "It is safe to turn off your device",
         "Stopping a12-diagnostics.service", "x" * 300, "Wq{}|~!@#$%^&*()_+[]"]

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    (tmp / "harness.c").write_text(HARNESS)
    subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-o", str(tmp / "gen-glyphs"), str(splash / "gen-glyphs.c"),
                    *ftflags], check=True)
    subprocess.run([str(tmp / "gen-glyphs"), font, str(tmp / "splash-glyphs.h")], check=True)
    subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-DSPLASH_TTF", f"-I{splash}", "-o", str(tmp / "ttf"),
                    str(tmp / "harness.c"), str(splash / "splash-draw.c"), str(splash / "splash-ttf.c"), *ftflags],
                   check=True)
    subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-DSPLASH_ATLAS", f"-I{splash}", f"-I{tmp}", "-o",
                    str(tmp / "atlas"), str(tmp / "harness.c"), str(splash / "splash-draw.c"),
                    str(splash / "splash-atlas.c")], check=True)
    env = dict(os.environ, A12_SPLASH_FONT=font)
    ttf = subprocess.run([str(tmp / "ttf"), *LINES], env=env, capture_output=True, check=True).stdout
    atlas = subprocess.run([str(tmp / "atlas"), *LINES], capture_output=True, check=True).stdout
    assert len(ttf) == len(atlas) == len(LINES) * 32 * 1024 * 4
    row = 32 * 1024 * 4
    for i, line in enumerate(LINES):
        a, b = ttf[i * row:(i + 1) * row], atlas[i * row:(i + 1) * row]
        assert any(a), line  # FreeType drew something
        assert a == b, f"atlas differs from FreeType for {line!r}"
print("splash atlas: ok")
