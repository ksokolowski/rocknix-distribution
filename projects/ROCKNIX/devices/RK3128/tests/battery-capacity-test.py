#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-battery: the capacity table and the median of the last samples.

The table comes from the 2026-10-27 baseline run on the owner's A12 (idle in
ES, 50 % brightness, Ethernet, boot 2d6972b9): each 5 % step is the voltage
at which that share of the usable idle runtime was left. 0 % is 3538 mV,
about 23 min before the cell cut out. 100 % is the median reading right
after unplugging a full cell (4144 mV, 2026-10-28, boot 74c5b413, 3.6 h on
the charger); 95 % lies halfway between 90 and 100 % until a run from full
measures it. One ADC sample every 5 s wobbles by tens of mV,
so the driver reports the median of the last five. It announces a change
(uevent) only when status, capacity or the charger differ from the last
reading: one every 5 s made udev start workers, and those forks kept
schedutil at 1200 MHz (2026-10-28).

a12_capacity, a12_median and a12_changed are extracted from the driver by their
`static int name(` ... `\\n}\\n` boundaries and built on the host.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
driver = (root / "projects/ROCKNIX/devices/RK3128/packages/rk3128-hardware/sources/a12-battery.c").read_text()


def function(name):
    m = re.search(r"^static int %s\(.*?\n}\n" % name, driver, re.S | re.M)
    assert m, name + " not found in a12-battery.c"
    return m.group(0)


harness = r"""
#include <stdio.h>
#include <string.h>
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define A12_SAMPLES 5
%s
%s
int main(int argc, char **argv)
{
    if (!strcmp(argv[1], "chg")) {
        int v[7];
        for (int i = 0; i < 7; i++)
            sscanf(argv[i + 2], "%%d", &v[i]);
        printf("%%d\n", a12_changed(v[0], v[1], v[2], v[3], v[4], v[5], v[6]));
    } else if (!strcmp(argv[1], "cap")) {
        for (int mv = 3400; mv <= 4300; mv++)
            printf("%%d %%d\n", mv, a12_capacity(mv));
    } else {
        int s[A12_SAMPLES], n = argc - 2;
        for (int i = 0; i < n; i++)
            sscanf(argv[i + 2], "%%d", &s[i]);
        printf("%%d\n", a12_median(s, n));
    }
    return 0;
}
""" % (function("a12_capacity"), function("a12_median") + function("a12_changed"))

with tempfile.TemporaryDirectory() as tmp:
    src, exe = pathlib.Path(tmp) / "t.c", pathlib.Path(tmp) / "t"
    src.write_text(harness)
    subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-Wno-sign-compare", str(src), "-o", str(exe)], check=True)
    cap = dict(tuple(map(int, l.split())) for l in subprocess.run([str(exe), "cap"], capture_output=True, text=True, check=True).stdout.splitlines())

    def median(*samples):
        return int(subprocess.run([str(exe), "med", *map(str, samples)], capture_output=True, text=True, check=True).stdout)

    assert cap[3400] == 0 and cap[3538] == 0, "0 % at 3538 mV and below"
    assert cap[4140] == 100 and cap[4300] == 100, "100 % at 4140 mV and above: a full cell"
    assert cap[4139] == 99
    # Points of the baseline run: voltage -> share of the usable runtime left.
    for mv, left in ((4069, 90), (3940, 80), (3865, 60), (3818, 45), (3731, 25), (3630, 10), (3583, 5)):
        assert abs(cap[mv] - left) <= 1, (mv, cap[mv], left)
    values = [cap[mv] for mv in range(3400, 4301)]
    assert values == sorted(values), "capacity never falls as the voltage rises"
    assert max(b - a for a, b in zip(values, values[1:])) <= 1, "no jump of more than 1 % per mV (old table: 6 % at 3772-3773)"

    def changed(*v):
        return int(subprocess.run([str(exe), "chg", *map(str, v)], capture_output=True, text=True, check=True).stdout)

    # (valid, old status, old capacity, old online, new status, new capacity, new online)
    assert changed(0, 0, 0, 0, 2, 80, 0) == 1, "the first reading is announced"
    assert changed(1, 2, 80, 0, 2, 80, 0) == 0, "same status, capacity and charger: no uevent"
    assert changed(1, 2, 80, 0, 2, 79, 0) == 1, "one percent less"
    assert changed(1, 2, 80, 0, 1, 80, 1) == 1, "charger plugged in"
    assert changed(1, 2, 80, 0, 3, 80, 0) == 1, "status only"

    assert median(3800, 3900, 3500, 3810, 3820) == 3810
    assert median(3800, 3500, 3820) == 3800
    assert median(3700) == 3700
    assert median(3500, 3900) in (3500, 3900)
print("battery capacity: ok")
