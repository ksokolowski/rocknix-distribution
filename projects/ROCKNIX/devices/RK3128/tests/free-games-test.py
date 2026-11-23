#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""A fresh A12 card has free games to play (sync9, more in sync11).

ROCKNIX ships no games. The A12 image carries Doom 1.9 shareware, which
id Software made freely distributable (John Carmack, 1999, quoted in
Debian's copyright file shipped next to it), taken from Debian's
doom-wad-shareware package at build time (no game data in the repo).
PrBoom embeds its own prboom.wad, so doom1.wad alone runs.
sync11 adds Freedoom 1 and 2 (BSD), Tobu Tobu Girl and its Deluxe remaster
(MIT code, CC BY 4.0 assets) and the homebrew Batocera ships (Old Towers,
Space Twins, Reflectron, Santatlantean; no licence file, included with
credits and removed on an author's request, owner 2026-10-25). Each is
fetched at build time from a fixed URL (release tag or commit) and checked
against its sha256; each system folder gets a licence or credits file.
All ran in the image's cores under QEMU (frames change, Freedoom 2 peaks
at 83 MB RSS against 29 MB for Doom shareware).

023-a12-free-games links each file into roms once and records it: a later
boot skips recorded files, so a deleted game stays deleted, a game a newer
image adds still arrives, and an existing file of the same name is never
replaced. The first version's marker was empty after seeding only Doom.
sync11 copied them, 63 s of a first boot for 65 MB the image already holds
(sync12 links them). RetroArch keeps saves next to the path it was given
(savefiles_in_content_dir; it resolves links only for its history list),
so saves stay in roms. A link whose game a newer image no longer ships is
removed.
"""
import os
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = root / "projects/ROCKNIX/devices/RK3128/packages/a12-free-games"
hook = pkg / "sources/023-a12-free-games"
mk = (pkg / "package.mk").read_text()
options = (root / "projects/ROCKNIX/devices/RK3128/options").read_text()

assert "a12-free-games" in re.search(r'^ADDITIONAL_PACKAGES="([^"]*)"', options, re.M)[1].split()
assert re.search(r'^PKG_URL="https://deb\.debian\.org/debian/pool/non-free/d/doom-wad-shareware/', mk, re.M)
assert re.search(r'^PKG_SHA256="[0-9a-f]{64}"', mk, re.M)
assert "/usr/lib/autostart/RK3128" in mk and "023-a12-free-games" in mk

# The extra downloads: "name url sha256", each URL fixed by a release tag or
# a 40-hex commit so the checksum cannot go stale under a moving branch.
files = re.search(r'^A12_FREE_GAMES_FILES="\n(.*?)^"', mk, re.M | re.S)
assert files, "package.mk lacks A12_FREE_GAMES_FILES"
fetched = {}
for line in files[1].splitlines():
    name, url, sha = line.split()
    assert url.startswith("https://") and sha == sha.lower() and len(sha) == 64, line
    assert re.search(r"/releases/download/v[\d.]+/|/[0-9a-f]{40}/", url), f"unpinned URL: {url}"
    fetched[name] = url
expected = {"freedoom-0.13.0.zip", "tobu.gb", "tobudx.gb", "Old-Towers.bin", "SpaceTwins.gba",
            "Reflectron.pce", "Santatlantean.pce"}
assert set(fetched) == expected, sorted(set(fetched) ^ expected)


def unpack(download):
    """Run unpack() with a fake download; return (exit status, output)."""
    with tempfile.TemporaryDirectory() as tmp:
        script = f'''
SOURCES={tmp}; PKG_BUILD={tmp}/build; PKG_NAME=a12-free-games; mkdir -p {tmp}/a12-free-games
die() {{ echo "die: $*"; exit 1; }}
ar() {{ :; }}; tar() {{ :; }}; unzip() {{ echo unzipped; }}
curl() {{ while [ "$1" != -o ]; do shift; done; printf {download} > "$2"; }}
. "{pkg}/package.mk" >/dev/null
A12_FREE_GAMES_FILES="
game.gb https://example.invalid/game.gb $(printf good | sha256sum | cut -d' ' -f1)
"
unpack
'''
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        return r.returncode, r.stdout


status, out = unpack("good")
assert status == 0 and "unzipped" in out, out
status, out = unpack("bad")
assert status != 0 and "game.gb does not match" in out and "unzipped" not in out, \
    f"a download that fails its sha256 must stop the build: {status} {out}"


def installed(script_body):
    """What makeinstall_target puts under usr/share/a12-free-games, from stub sources."""
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        build, inst, src = t / "build", t / "install", t / "sources/a12-free-games"
        (build / "usr/share/games/doom").mkdir(parents=True)
        (build / "usr/share/games/doom/doom1.wad").write_text("x")
        (build / "usr/share/doc/doom-wad-shareware").mkdir(parents=True)
        (build / "usr/share/doc/doom-wad-shareware/copyright").write_text("x")
        fd = build / "freedoom-0.13.0"
        fd.mkdir()
        for n in ("freedoom1.wad", "freedoom2.wad", "COPYING.txt", "CREDITS.txt"):
            (fd / n).write_text("x")
        src.mkdir(parents=True)
        for n in fetched:
            (src / n).write_text("x")
        script = f'''
PKG_BUILD={build}; INSTALL={inst}; SOURCES={t}/sources; PKG_DIR={pkg}; PKG_NAME=a12-free-games
. "{pkg}/package.mk" >/dev/null
{script_body}
'''
        subprocess.run(["bash", "-c", script], check=True)
        share = inst / "usr/share/a12-free-games"
        return {str(p.relative_to(share)) for p in share.rglob("*") if p.is_file()}


got = installed("makeinstall_target")
for game in ("doom/doom1.wad", "doom/freedoom1.wad", "doom/freedoom2.wad", "gb/Tobu Tobu Girl.gb",
             "gb/Tobu Tobu Girl Deluxe.gb", "megadrive/Old Towers.bin", "gba/Space Twins.gba",
             "pcengine/Reflectron.pce", "pcengine/Santatlantean.pce"):
    assert game in got, f"{game} not installed: {sorted(got)}"
for system in {g.split("/")[0] for g in got}:
    assert any(g.startswith(system + "/") and g.endswith(".txt") for g in got), f"{system} has no licence/credits file"
assert "doom/freedoom.COPYING.txt" in got and "doom/freedoom.CREDITS.txt" in got


def run(fake):
    subprocess.run(["bash", str(hook)], env={"A12_ROOT": str(fake), "PATH": os.environ["PATH"]}, check=True)


with tempfile.TemporaryDirectory() as tmp:
    fake = pathlib.Path(tmp)
    src = fake / "usr/share/a12-free-games/doom"
    src.mkdir(parents=True)
    (src / "doom1.wad").write_bytes(b"IWAD shareware")
    (src / "doom1.wad.copyright.txt").write_text("freely distributable\n")
    doom = fake / "storage/roms/doom"
    doom.mkdir(parents=True)
    (fake / "storage/.cache").mkdir(parents=True)
    marker = fake / "storage/.cache/a12-free-games.seeded"

    run(fake)
    assert (doom / "doom1.wad").read_bytes() == b"IWAD shareware", "first boot must seed doom1.wad"
    assert (doom / "doom1.wad").is_symlink() and os.readlink(doom / "doom1.wad") == str(src / "doom1.wad"), \
        "games are links into the image, not copies"
    assert (doom / "doom1.wad.copyright.txt").exists(), "the licence goes next to it"

    (doom / "doom1.wad").unlink()
    run(fake)
    assert not (doom / "doom1.wad").exists(), "a deleted game must stay deleted"

    # A newer image adds a game: it reaches the already seeded card once.
    gb = fake / "usr/share/a12-free-games/gb"
    gb.mkdir()
    (gb / "Tobu Tobu Girl.gb").write_bytes(b"tobu")
    run(fake)
    assert (fake / "storage/roms/gb/Tobu Tobu Girl.gb").read_bytes() == b"tobu", "a new game must be seeded"
    assert not (doom / "doom1.wad").exists(), "seeding a new game must not bring back a deleted one"

    # A card that already had its own doom1.wad before the first seeding.
    marker.unlink()
    (doom / "doom1.wad").write_bytes(b"owner's registered copy")
    run(fake)
    assert (doom / "doom1.wad").read_bytes() == b"owner's registered copy", "never replace a file"

    # The first version left an empty marker after seeding Doom only: Doom
    # counts as seeded, the rest is new.
    marker.write_text("")
    (doom / "doom1.wad").unlink()
    (fake / "storage/roms/gb/Tobu Tobu Girl.gb").unlink()
    run(fake)
    assert not (doom / "doom1.wad").exists(), "an old marker must keep a deleted Doom deleted"
    assert (fake / "storage/roms/gb/Tobu Tobu Girl.gb").exists(), "an old marker must not block new games"

    # A newer image drops a game: its link goes, the owner's files stay.
    (fake / "storage/roms/gb/own.gb").write_bytes(b"mine")
    (gb / "Tobu Tobu Girl.gb").unlink()
    run(fake)
    assert not os.path.lexists(fake / "storage/roms/gb/Tobu Tobu Girl.gb"), "a dangling game link must go"
    assert (fake / "storage/roms/gb/own.gb").exists()

    # No source (other image) or no roms folder: nothing happens.
    empty = fake / "other"
    (empty / "storage/.cache").mkdir(parents=True)
    run(empty)
    assert not (empty / "storage/roms").exists()

image = root / "build.ROCKNIX-RK3128.arm/image/system/usr/share/a12-free-games"
if (image / "gb").is_dir():
    have = {str(p.relative_to(image)) for p in image.rglob("*") if p.is_file()}
    assert have == got, f"built image differs from the package: {sorted(have ^ got)}"
    print("free games: ok (built image checked)")
else:
    print("free games: ok")
