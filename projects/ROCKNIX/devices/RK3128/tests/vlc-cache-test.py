#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-vlc-cache builds VLC's plugins.dat on /storage (VLC brief, task 3).

Without the cache every libVLC instance dlopen()s and keeps every plugin
(qemu-arm, ES's preview calls: 266 plugin files mapped with the full
plugin set, 48 trimmed, 24 trimmed with the cache). /usr is read-only and
VLC only reads <plugin dir>/plugins.dat, so the image links it to
/storage/.cache/vlc/plugins/plugins.dat and a12-vlc-cache runs
vlc-cache-gen on a mirror of the plugin tree made of symlinks, before ES,
again only when a plugin's size or mtime changes (what VLC checks).
Here vlc-cache-gen is a mock that records its calls.
"""
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
dev = root / "projects/ROCKNIX/devices/RK3128"
script = dev / "packages/a12-controls/sources/a12-vlc-cache"
unit = (dev / "packages/a12-controls/sources/a12-vlc-cache.service").read_text()
mk = (dev / "packages/a12-controls/package.mk").read_text()

assert "Before=emustation.service" in unit and "RequiresMountsFor=/storage" in unit
assert "ExecStart=/usr/bin/a12-vlc-cache\n" in unit and "Type=oneshot" in unit
assert "ConditionPathExists=/usr/lib/vlc/vlc-cache-gen" in unit and "WantedBy=rocknix.target" in unit
assert '"${PKG_BUILD}/a12-vlc-cache" "${INSTALL}/usr/bin/"' in mk
assert "enable_service a12-vlc-cache.service" in mk

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    plugins = tmp / "usr/lib/vlc/plugins"
    for rel in ("codec/libavcodec_plugin.so", "demux/libmp4_plugin.so", "video_output/libvmem_plugin.so"):
        (plugins / rel).parent.mkdir(parents=True, exist_ok=True)
        (plugins / rel).write_bytes(b"\x7fELF" + rel.encode())
    calls = tmp / "calls"
    gen = tmp / "vlc-cache-gen"
    # Like vlc-cache-gen: one cache per directory argument, entries by
    # relative path with the size and mtime it sees through the symlinks.
    gen.write_text(f"""#!/bin/sh
echo "$1" >> {calls}
[ -n "$FAIL" ] && exit 1
cd "$1" && find . -name '*.so' | sort | while read -r f; do
  [ -L "$f" ] || echo "not a symlink: $f"
  echo "$f $(stat -L -c '%s %Y' "$f")"
done > plugins.dat
""")
    gen.chmod(0o755)
    cache = tmp / "storage/.cache/vlc/plugins"
    env = dict(os.environ, A12_VLC_PLUGINS=str(plugins), A12_VLC_CACHE=str(cache), A12_VLC_CACHE_GEN=str(gen))

    def run(**extra):
        return subprocess.run(["sh", str(script)], env=dict(env, **extra), capture_output=True, text=True)

    def ncalls():
        return len(calls.read_text().splitlines()) if calls.exists() else 0

    assert run().returncode == 0 and ncalls() == 1
    assert calls.read_text().strip() == f"{cache}.new", calls.read_text()
    dat = (cache / "plugins.dat").read_text()
    assert "not a symlink" not in dat and len(dat.splitlines()) == 3, dat
    link = cache / "codec/libavcodec_plugin.so"
    assert link.is_symlink() and os.readlink(link) == str(plugins / "codec/libavcodec_plugin.so")
    assert not pathlib.Path(f"{cache}.new").exists()

    assert run().returncode == 0 and ncalls() == 1, "unchanged plugins: no rebuild"

    so = plugins / "demux/libmp4_plugin.so"
    os.utime(so, (1_000_000_000, 1_000_000_000))
    assert run().returncode == 0 and ncalls() == 2, "a changed plugin rebuilds the cache"
    assert f"./demux/libmp4_plugin.so {so.stat().st_size} 1000000000" in (cache / "plugins.dat").read_text()

    # A failed rebuild keeps the previous cache and leaves no partial tree.
    so.write_bytes(b"\x7fELF bigger")
    before = (cache / "plugins.dat").read_text()
    r = run(FAIL="1")
    assert r.returncode == 1 and ncalls() == 3
    assert (cache / "plugins.dat").read_text() == before
    assert not pathlib.Path(f"{cache}.new").exists()
    assert run().returncode == 0 and ncalls() == 4
print("vlc cache: ok")
