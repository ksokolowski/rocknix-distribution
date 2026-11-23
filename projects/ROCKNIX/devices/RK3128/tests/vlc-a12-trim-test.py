#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""VLC on the A12 is built and installed only for what ES needs (VLC brief, tasks 1-3).

ES uses libVLC for preview videos (vmem RGBA, ALSA audio) and thumbnails
(scene filter, JPEG/PNG encoders, dummy vout). On RK3128 package.mk swaps
the configure set for a trimmed one (no network, streaming, encoders, GL),
keeps --enable-sout because the image encoders behind snapshots live in
the core's sout code, links with -z noexecstack, keeps only the listed
plugins and links plugins.dat to the cache a12-vlc-cache builds on
/storage. Other devices keep the shared configuration. When an A12 VLC
install exists (A12_VLC_INSTALL or the build directory), its plugins must
match the list and no shared object may ask for an executable stack.
"""
import glob
import os
import pathlib
import shutil
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = root / "projects/ROCKNIX/packages/multimedia/vlc/package.mk"


def evaluate(device, install=None):
    script = f"""
DEVICE={device}; ARCH=arm; TOOLCHAIN=/t; OPENGLES=mesa; LDFLAGS=""; INSTALL="{install or ''}"
. "{pkg}"
pre_configure_target
echo "DEPS=$PKG_DEPENDS_TARGET"
echo "OPTS=$PKG_CONFIGURE_OPTS_TARGET"
echo "LDFLAGS=$LDFLAGS"
echo "PLUGINS=$(echo $A12_VLC_PLUGINS)"
{'post_makeinstall_target' if install else ''}
"""
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout
    keys = ("DEPS=", "OPTS=", "LDFLAGS=", "PLUGINS=")
    vals = dict(line.split("=", 1) for line in out.splitlines() if line.startswith(keys))
    return vals["DEPS"].split(), vals["OPTS"].split(), vals["LDFLAGS"], vals["PLUGINS"].split()


deps, opts, ldflags, plugins = evaluate("RK3128")
assert sorted(deps) == sorted("toolchain ffmpeg zlib alsa-lib libpng libjpeg-turbo".split()), deps
for opt in ("--enable-avcodec", "--enable-avformat", "--enable-swscale", "--enable-neon",
            "--enable-png", "--enable-jpeg", "--enable-alsa", "--enable-vlc",
            "--enable-optimize-memory", "--enable-sout"):
    assert opt in opts, opt
for opt in ("--disable-pulse", "--disable-x264", "--disable-libmpeg2", "--disable-gnutls",
            "--disable-lua", "--disable-vlm", "--disable-gles2", "--disable-libxml2",
            "--disable-live555", "--disable-upnp", "--disable-chromecast", "--disable-udev"):
    assert opt in opts, opt
names = [o.split("=")[0].replace("--enable-", "").replace("--disable-", "") for o in opts
         if o.startswith(("--enable-", "--disable-"))]
assert len(names) == len(set(names)), "an option is both enabled and disabled"
assert "-Wl,-z,noexecstack" in ldflags.split() and "-fopenmp" not in ldflags, ldflags

# ES's preview and thumbnail paths (verified with ES's libVLC calls under
# qemu-arm on a cross-built trimmed install, 2026-10-12).
for plugin in ("access/libfilesystem_plugin.so", "demux/libmp4_plugin.so",
               "demux/libavformat_plugin.so", "codec/libavcodec_plugin.so",
               "packetizer/libpacketizer_h264_plugin.so",
               "packetizer/libpacketizer_mpeg4audio_plugin.so",
               "video_chroma/libswscale_plugin.so", "video_chroma/libyuvp_plugin.so",
               "arm_neon/libyuv_rgb_neon_plugin.so", "video_output/libvmem_plugin.so",
               "video_output/libvdummy_plugin.so", "audio_output/libalsa_plugin.so",
               "audio_output/libadummy_plugin.so", "audio_filter/libscaletempo_plugin.so",
               "video_filter/libscene_plugin.so", "codec/libjpeg_plugin.so",
               "codec/libpng_plugin.so", "control/libdummy_plugin.so"):
    assert plugin in plugins, plugin
assert len(plugins) == len(set(plugins))
for d in ("stream_out", "mux", "services_discovery", "lua", "visualization", "gui", "keystore"):
    assert not any(p.split("/")[0] == d for p in plugins), d
for word in ("http", "x264", "gnutls", "gles2"):
    assert not any(word in p for p in plugins), word

with tempfile.TemporaryDirectory() as tmp:
    inst = pathlib.Path(tmp)
    lib = inst / "usr/lib/vlc/plugins"
    extra = ["access/libhttp_plugin.so", "stream_out/libstream_out_standard_plugin.so",
             "codec/libx264_plugin.so", "visualization/libvisual_plugin.so"]
    for p in plugins + extra:
        (lib / p).parent.mkdir(parents=True, exist_ok=True)
        (lib / p).write_bytes(b"\x7fELF")
    (inst / "usr/lib/vlc/vlc-cache-gen").write_bytes(b"\x7fELF")
    (inst / "usr/bin").mkdir(parents=True)
    for b in ("vlc", "cvlc", "rvlc", "vlc-wrapper"):
        (inst / "usr/bin" / b).write_text("#!/bin/sh\n")
    (inst / "usr/share/vlc/utils").mkdir(parents=True)
    evaluate("RK3128", inst)
    kept = sorted(str(p.relative_to(lib)) for p in lib.rglob("*.so"))
    assert kept == sorted(plugins), set(kept) ^ set(plugins)
    assert not (lib / "visualization").exists() and not (lib / "stream_out").exists()
    assert os.readlink(lib / "plugins.dat") == "/storage/.cache/vlc/plugins/plugins.dat"
    assert (inst / "usr/lib/vlc/vlc-cache-gen").exists()
    assert (inst / "usr/bin/cvlc").exists() and not (inst / "usr/bin/rvlc").exists()
    assert not (inst / "usr/share/vlc").exists()

# Other devices keep the shared configuration and every plugin.
deps, opts, ldflags, plugins = evaluate("RK3326")
assert "--enable-x264" in opts and "--enable-pulse" in opts and "--enable-gles2" in opts, opts
assert "x264" in deps and "pulseaudio" in deps, deps
assert "-fopenmp" in ldflags and not plugins
with tempfile.TemporaryDirectory() as tmp:
    inst = pathlib.Path(tmp)
    (inst / "usr/lib/vlc/plugins/access").mkdir(parents=True)
    (inst / "usr/lib/vlc/plugins/access/libhttp_plugin.so").write_bytes(b"")
    evaluate("RK3326", inst)
    assert (inst / "usr/lib/vlc/plugins/access/libhttp_plugin.so").exists()
    assert not (inst / "usr/lib/vlc/plugins/plugins.dat").exists()

# A build output: the installed plugin set and the stack flags.
install = os.environ.get("A12_VLC_INSTALL") or next(
    iter(sorted(glob.glob(str(root / "build.ROCKNIX-RK3128.arm/install_pkg/vlc-*")))), None)
if install and shutil.which("readelf"):
    _, _, _, plugins = evaluate("RK3128")
    lib = pathlib.Path(install) / "usr/lib/vlc/plugins"
    kept = sorted(str(p.relative_to(lib)) for p in lib.rglob("*.so"))
    assert kept == sorted(plugins), set(kept) ^ set(plugins)
    rwe = []
    for so in pathlib.Path(install).rglob("*.so*"):
        if so.is_file() and not so.is_symlink():
            out = subprocess.run(["readelf", "-lW", str(so)], capture_output=True, text=True).stdout
            if any(line.split()[:1] == ["GNU_STACK"] and "E" in line.split()[-2] for line in out.splitlines()):
                rwe.append(str(so))
    assert not rwe, f"executable stack requested by {rwe}"
    print(f"vlc a12 trim: ok ({len(kept)} plugins in {install}, no executable stacks)")
else:
    print("vlc a12 trim: ok (no A12 VLC build output; install check not run)")
