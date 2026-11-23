#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""ES at an idle menu: fewer wakeups and no resampled silence (test 60).

With PowerSaverMode "enhanced" ES presents no frames at idle but still used
≈7 % of a core (test 59): SDL2's SDL_WaitEventTimeout has no KMSDRM backend
wait and its fallback loop pumps events every EVENT_POLL_INTERVAL_MS (1 ms),
and ES opened audio at 44.1 kHz on a 48 kHz device, so silence was resampled
continuously. A12 SDL2 patch 0001 sleeps 10 ms in that fallback loop only;
A12 ES patch 0002 opens audio at 48 kHz. Check both against the pinned
sources.

With the screen dark the 10 ms loop still woke ES about 100 times a second
(2026-10-28). Patch 0001 now backs off: 10 ms while events arrive, 100 ms
once none has come for a second, never past the caller's timeout. The delay
choice is compiled from the patched source and checked here.
"""
import pathlib
import re
import shutil
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
dev = root / "projects/ROCKNIX/devices/RK3128/patches"


def patched(pkgdir, name, member, patch):
    pkg = (root / pkgdir / "package.mk").read_text()
    version = re.search(r'^PKG_VERSION="([^"]+)"', pkg, re.M)[1]
    tarball = root / f"sources/{name}/{name}-{version}.tar.gz"
    if not tarball.exists():
        print(f"note: {name} source tarball not downloaded; skipped")
        return None
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        with tarfile.open(tarball) as tar:
            m = next(m for m in tar.getmembers() if m.name.endswith("/" + member))
            m.name = member
            tar.extract(m, tmp, filter="data")
        subprocess.run(["patch", "-p1", "-s", "-d", str(tmp)], input=patch.read_text(encoding="latin-1"),
                       text=True, encoding="latin-1", check=True)
        return (tmp / member).read_text(encoding="latin-1")


sdl = patched("projects/ROCKNIX/packages/graphics/SDL2", "SDL2", "src/events/SDL_events.c",
              dev / "SDL2/0001-events-back-off-in-the-fallback-wait-loop.patch")
if sdl is not None:
    assert "#define EVENT_POLL_INTERVAL_MS 1\n" in sdl  # sensor/joystick polling unchanged
    loop = sdl[sdl.index("int SDL_WaitEventTimeout(SDL_Event *event, int timeout)"):]
    loop = loop[:loop.index("\nint SDL_PushEvent(")]
    delays = re.findall(r"SDL_Delay\(([^;]+)\);", loop)
    assert delays == ["SDL_WaitFallbackDelay(SDL_GetTicks(), timeout, expiration)"], delays
    assert loop.count("SDL_last_wait_event = SDL_GetTicks();") == 2, "both event returns mark activity"
    start = sdl.index("static Uint32 SDL_WaitFallbackDelay(")
    func = sdl[start:sdl.index("\n}\n", start) + 3]
    defines = "".join(re.findall(r"#define EVENT_WAIT_\w+ \d+\n", sdl))
    cc = shutil.which("cc") or shutil.which("gcc")
    with tempfile.TemporaryDirectory() as tmp:
        c = pathlib.Path(tmp) / "t.c"
        c.write_text(f"""#include <assert.h>
#include <stdint.h>
typedef uint32_t Uint32;
typedef int32_t Sint32;
#define SDL_TICKS_PASSED(A, B) ((Sint32)((B) - (A)) <= 0)
{defines}static Uint32 SDL_last_wait_event;
{func}
int main(void)
{{
    SDL_last_wait_event = 5000;
    assert(SDL_WaitFallbackDelay(5500, -1, 0) == 10);      /* events arriving: stay quick */
    assert(SDL_WaitFallbackDelay(5999, -1, 0) == 10);
    assert(SDL_WaitFallbackDelay(6000, -1, 0) == 100);     /* idle a second: back off */
    assert(SDL_WaitFallbackDelay(90000, -1, 0) == 100);
    assert(SDL_WaitFallbackDelay(6000, 500, 6030) == 30);  /* never past the timeout */
    assert(SDL_WaitFallbackDelay(5500, 500, 5503) == 3);
    assert(SDL_WaitFallbackDelay(6000, 500, 6000) == 1);
    assert(SDL_WaitFallbackDelay(6000, 500, 9000) == 100);
    SDL_last_wait_event = 0xfffffff0u;                    /* tick counter wraps */
    assert(SDL_WaitFallbackDelay(0x10, -1, 0) == 10);
    assert(SDL_WaitFallbackDelay(0x1000, -1, 0) == 100);
    return 0;
}}
""")
        subprocess.run([cc, "-Wall", "-Wextra", "-Werror", "-o", str(c.with_suffix("")), str(c)], check=True)
        subprocess.run([str(c.with_suffix(""))], check=True)

es = patched("projects/ROCKNIX/packages/ui/emulationstation", "emulationstation", "es-core/src/AudioManager.cpp",
             dev / "emulationstation/0002-audio-open-the-device-at-48-khz.patch")
if es is not None:
    assert "Mix_OpenAudio(48000, MIX_DEFAULT_FORMAT, 2, 4096)" in es
    assert "Mix_OpenAudio(44100" not in es
print("es idle cost: ok")
