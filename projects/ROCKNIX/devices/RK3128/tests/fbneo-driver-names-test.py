#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""FBNeo copies a driver's names only when they change (A12 patch 0001).

Upstream BurnGameListInit() allocated and zero-filled writable names for all
~28,700 drivers (≈39 MiB of heap per session). The patched functions are
taken from the pinned FBNeo source with the patch applied, compiled against
mock drivers, and checked: no allocation at init, a rename touches only its
driver, exit restores the built-in names, long names are truncated.
"""
import pathlib
import re
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = (root / "projects/ROCKNIX/packages/emulators/libretro/fbneo-lr/package.mk").read_text()
version = re.search(r'^PKG_VERSION="([0-9a-f]+)"', pkg, re.M)[1]
tarball = root / f"sources/fbneo-lr/fbneo-lr-{version}.tar.gz"
patch = root / "projects/ROCKNIX/devices/RK3128/patches/fbneo-lr/0001-burn-copy-driver-names-only-when-changed.patch"

HARNESS_HEAD = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
typedef unsigned int UINT32;
typedef int INT32;
typedef char TCHAR;
#define MAX_PATH 260
struct BurnDriver { char* szShortName; char* szFullNameA; wchar_t* szFullNameW; };
static char s0[] = "ffight", s1[] = "ffightu", s2[] = "ffightj";
static char f0[] = "Final Fight (World)", f1[] = "Final Fight (USA)", f2[] = "Final Fight (Japan)";
static BurnDriver d0 = { s0, f0, NULL }, d1 = { s1, f1, NULL }, d2 = { s2, f2, NULL };
static BurnDriver* pDriver[] = { &d0, &d1, &d2 };
static UINT32 nBurnDrvCount = 3;
static UINT32 nBurnDrvActive = 0;
static size_t nAllocs;
static void* count_calloc(size_t n, size_t s) { nAllocs++; return calloc(n, s); }
#define calloc count_calloc
#define malloc(n) (nAllocs++, malloc(n))
'''

HARNESS_MAIN = r'''
#undef calloc
int main()
{
	BurnGameListInit();
	assert(nAllocs == 0);
	assert(d0.szShortName == s0 && d1.szFullNameA == f1 && d2.szShortName == s2);

	assert(BurnDrvSetZipName((char*)"ffightx", 1) == 0);
	assert(BurnDrvSetFullNameA((char*)"Final Fight (custom)", 1) == 0);
	assert(nAllocs == 1);
	assert(strcmp(d1.szShortName, "ffightx") == 0 && strcmp(d1.szFullNameA, "Final Fight (custom)") == 0);
	assert(d0.szShortName == s0 && d2.szFullNameA == f2);

	char longname[400];
	memset(longname, 'x', sizeof(longname) - 1);
	longname[sizeof(longname) - 1] = '\0';
	assert(BurnDrvSetZipName(longname, 2) == 0);
	assert(strlen(d2.szShortName) == 99);
	assert(BurnDrvSetFullNameA(longname, 2) == 0);
	assert(strlen(d2.szFullNameA) == MAX_PATH - 1);
	assert(BurnDrvSetZipName((char*)"bad", 7) == -1);

	BurnGameListExit();
	assert(d1.szShortName == s1 && d1.szFullNameA == f1 && d2.szShortName == s2 && d2.szFullNameA == f2);
	BurnGameListInit();
	assert(BurnDrvSetZipName((char*)"again", 1) == 0 && strcmp(d1.szShortName, "again") == 0);
	BurnGameListExit();
	assert(d1.szShortName == s1);
	puts("fbneo driver names: ok");
	return 0;
}
'''


def block(code, start, end):
    a = code.index(start)
    return code[a:code.index(end, a)]


if not tarball.exists():
    print("note: FBNeo source tarball not downloaded; fbneo driver names skipped")
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    with tarfile.open(tarball) as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith("/src/burn/burn.cpp"))
        member.name = "src/burn/burn.cpp"
        tar.extract(member, tmp, filter="data")
    subprocess.run(["patch", "-p1", "-s", "-d", str(tmp)], input=patch.read_text(), text=True, check=True)
    code = (tmp / "src/burn/burn.cpp").read_text()
    parts = [
        block(code, "struct BurnNameCopy {", "bool BurnCheckMMXSupport()"),
        block(code, "static void BurnGameListInit()", 'extern "C" INT32 BurnLibInit()'),
        block(code, "static INT32 BurnDrvSetFullNameA(", "INT32 BurnDrvSetFullNameW("),
        block(code, 'extern "C" INT32 BurnDrvSetZipName(', "\n}\n") + "\n}\n",
    ]
    source = HARNESS_HEAD + "\n".join(parts).replace('extern "C" ', "") + HARNESS_MAIN
    (tmp / "harness.cpp").write_text(source)
    subprocess.run(["g++", "-Wall", "-Wno-unused-function", "-o", str(tmp / "harness"), str(tmp / "harness.cpp")], check=True)
    subprocess.run([str(tmp / "harness")], check=True)
