#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""VLC's NEON converter turns planar YUV into ES's RGBA (A12 patch 0003).

ES asks libVLC for RGBA; no NEON converter offered it, so previews went
through swscale's C code (A12 perf: hScale8To15_c, yuv2rgbx32_full_2_c,
more CPU than the H.264 decoding; ES's previews are 4:4:4). The patch adds
an RGBA output for I420/YV12/I422/I444 with swscale's BT.601 matrix and
compares visible sizes (decoded pictures are padded). With the pinned
tarball, an ARM cross compiler and qemu-arm, the row converters run as ARM
code: NEON and scalar paths must agree bit for bit on every (Y, U, V), stay
within 1 of the exact BT.601 result, and alpha must be 255.
"""
import pathlib
import re
import shutil
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = (root / "projects/ROCKNIX/packages/multimedia/vlc/package.mk").read_text()
version = re.search(r'^PKG_VERSION="([^"]+)"', pkg, re.M)[1]
tarball = root / f"sources/vlc/vlc-{version}.tar.xz"
patch = root / "projects/ROCKNIX/devices/RK3128/patches/vlc/0003-arm_neon-convert-planar-YUV-to-RGBA.patch"
name = "modules/arm_neon/yuv_rgb.c"

if not tarball.exists():
    print("note: VLC source tarball not downloaded; RGBA converter check skipped")
    raise SystemExit(0)

HARNESS = r"""
#include <arm_neon.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "block.c"

static int ref(double v) { v = floor(v + 0.5); return v < 0 ? 0 : v > 255 ? 255 : (int)v; }

int main(void)
{
    enum { W = 256 + 7 };   /* NEON blocks plus a scalar tail */
    static uint8_t y[W], u[W], v[W], out[4 * W], one[4];
    int maxerr = 0, bad = 0;

    for (int cu = 0; cu < 256; cu++)
        for (int cv = 0; cv < 256; cv++) {
            for (int x = 0; x < W; x++) { y[x] = x & 255; u[x] = cu; v[x] = cv; }
            yuv_rgba_row(out, y, u, v, W, 0);
            for (int x = 0; x < W; x++) {
                yuv_rgba_pixel(one, y[x], cu, cv);
                for (int c = 0; c < 4; c++)
                    if (out[4 * x + c] != one[c]) bad++;
                double l = 1.164383 * (y[x] - 16);
                int e[3] = { ref(l + 1.596027 * (cv - 128)),
                             ref(l - 0.391762 * (cu - 128) - 0.812968 * (cv - 128)),
                             ref(l + 2.017232 * (cu - 128)) };
                for (int c = 0; c < 3; c++) {
                    int d = abs(out[4 * x + c] - e[c]);
                    if (d > maxerr) maxerr = d;
                }
                if (out[4 * x + 3] != 255) bad++;
            }
        }

    /* 4:2:x: one chroma sample for two pixels, NEON blocks of 16 */
    srand(1);
    for (int n = 0; n < 2000; n++) {
        int w = 1 + rand() % W;
        for (int x = 0; x < W; x++) { y[x] = rand(); u[x] = rand(); v[x] = rand(); }
        yuv_rgba_row(out, y, u, v, w, 1);
        for (int x = 0; x < w; x++) {
            yuv_rgba_pixel(one, y[x], u[x >> 1], v[x >> 1]);
            for (int c = 0; c < 4; c++)
                if (out[4 * x + c] != one[c]) bad++;
        }
        uint8_t mix[W];
        yuv_rgba_chroma_rows(mix, u, v, w);
        for (int x = 0; x < w; x++)
            if (mix[x] != (3 * u[x] + v[x] + 2) >> 2) bad++;
    }
    printf("%d %d\n", bad, maxerr);
    return 0;
}
"""

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    with tarfile.open(tarball) as tar:
        m = next(m for m in tar.getmembers() if m.name.endswith("/" + name))
        m.name = name
        tar.extract(m, tmp, filter="data")
    subprocess.run(["patch", "-p1", "-s", "-d", str(tmp)], input=patch.read_text(), text=True, check=True)
    code = (tmp / name).read_text()

    # Open(): RGBA for the four planar formats, visible sizes, no offsets.
    rgba = code[code.index("case VLC_CODEC_RGBA:"):]
    rgba = rgba[:rgba.index("break;\n#endif")]
    for chroma in ("I420", "YV12", "I422", "I444"):
        assert f"case VLC_CODEC_{chroma}:" in rgba, chroma
    assert "YUV_RGBA_Filter" in rgba
    assert "fmt_in.video.i_visible_width != filter->fmt_out.video.i_visible_width" in code
    assert "fmt_in.video.i_x_offset" in code
    assert "fmt_in.video.i_width != filter->fmt_out.video.i_width" not in code

    cc = shutil.which("arm-linux-gnueabihf-gcc")
    qemu = shutil.which("qemu-arm-static") or shutil.which("qemu-arm")
    if not cc or not qemu:
        print("note: arm-linux-gnueabihf-gcc or qemu-arm not installed; RGBA converter run skipped")
        raise SystemExit(0)
    start = code.index("#define YUV_RGBA_CY")
    end = code.index("static void YUV_RGBA (filter_t")
    (tmp / "block.c").write_text(code[start:end])
    (tmp / "harness.c").write_text(HARNESS)
    subprocess.run([cc, "-static", "-O2", "-march=armv7-a", "-mfpu=neon-vfpv4", "-mfloat-abi=hard",
                    "-Wall", "-Wextra", "-Werror", "-I", str(tmp), "-o", str(tmp / "harness"),
                    str(tmp / "harness.c"), "-lm"], check=True)
    out = subprocess.run([qemu, str(tmp / "harness")], capture_output=True, text=True, check=True).stdout
    bad, maxerr = map(int, out.split())
    assert bad == 0, f"{bad} NEON/scalar/alpha mismatches"
    assert maxerr <= 1, f"BT.601 error {maxerr}"
print(f"vlc yuv rgba: ok (NEON = scalar on all 16.7M YUV triples, BT.601 error <= {maxerr})")
