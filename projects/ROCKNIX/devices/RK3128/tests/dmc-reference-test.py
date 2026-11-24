#!/usr/bin/env python3
"""Check the compiled A12 DMC against the owner's live DT and vendor ABI.

Usage: dmc-reference-test.py DTB LIVE_DTS VENDOR_KERNEL MODULE
Requires dtc, fdtget and modinfo. Reference repositories are read-only.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def prop(dtb, node, name, kind="u"):
    return run("fdtget", "-t", kind, str(dtb), node, name)


def constant(source, name):
    match = re.search(r"^#define\s+" + re.escape(name) + r"\s+\(?(0x[\da-fA-F]+|\d+)\b", source, re.M)
    assert match, name
    return int(match[1], 0)


def struct_fields(source, name):
    body = re.search(r"struct\s+" + name + r"\s*\{(.*?)\};", source, re.S)[1]
    return re.findall(r"\bu32\s+(\w+)\s*;", body)


dtb, live_dts, vendor_kernel, module = map(Path, sys.argv[1:])
device = Path(__file__).resolve().parents[1]
driver = (device / "packages/rk3128-hardware/sources/a12-dmc.c").read_text()
vendor_devfreq = (vendor_kernel / "drivers/devfreq/rockchip_dmc.c").read_text()
vendor_clock = (vendor_kernel / "drivers/clk/rockchip/clk-ddr.c").read_text()
vendor_sip = (vendor_kernel / "include/linux/rockchip/rockchip_sip.h").read_text()
vendor_dram = (vendor_kernel / "include/soc/rockchip/rockchip_sip.h").read_text()
vendor_screen = (vendor_kernel / "include/dt-bindings/display/rk_fb.h").read_text()

assert struct_fields(driver, "a12_dram_params") == struct_fields(vendor_clock, "share_params")
assert struct_fields(driver, "a12_dram_params") == struct_fields(vendor_devfreq, "share_params")
for ours, theirs in [("DRAM_INIT", "INIT"), ("DRAM_SET_RATE", "SET_RATE"),
                     ("DRAM_ROUND_RATE", "ROUND_RATE"), ("DRAM_GET_RATE", "GET_RATE")]:
    assert constant(driver, ours) == constant(vendor_dram, "ROCKCHIP_SIP_CONFIG_DRAM_" + theirs)
for name in ("SIP_DRAM_CONFIG", "SIP_SHARE_MEM", "SIP_SIP_VERSION", "SIP_IMPLEMENT_V2", "SECURE_REG_WR"):
    assert constant(driver, name) == constant(vendor_sip, name)
assert constant(driver, "SCREEN_LVDS") == constant(vendor_screen, "SCREEN_LVDS")

names = struct_fields(vendor_devfreq, "rk3128_ddr_dts_config_timing")[:-1]
assert len(names) == 21
ours = re.search(r"timing_names\[\]\s*=\s*\{(.*?)\};", driver, re.S)[1]
assert re.findall(r'"(\w+)"', ours) == names, "Firmware timing field order differs"

with tempfile.TemporaryDirectory() as temporary:
    live_dtb = Path(temporary) / "live.dtb"
    compiled = subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-o", str(live_dtb), str(live_dts)],
                              capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    for name in names:
        assert prop(dtb, "/ddr-timing", name) == prop(live_dtb, "/ddr_timing", name), name
    assert prop(dtb, "/dmc", "vop-dclk-mode") == prop(live_dtb, "/dmc", "vop-dclk-mode")
    assert prop(dtb, "/dmc", "min-cpu-freq") == prop(live_dtb, "/dmc", "min-cpu-freq") == "600000"
    assert prop(dtb, "/dmc", "compatible", "s") == "powkiddy,a12-rev-a-dmc"
    status = subprocess.run(["fdtget", "-t", "s", str(dtb), "/dmc", "status"], capture_output=True, text=True)
    assert status.returncode != 0 or status.stdout.strip() == "okay", "DDR 456 MHz is the A12 default (TEST_LOG tests 30-33)"
    assert prop(dtb, "/dmc", "rockchip,ddr_timing") == prop(dtb, "/ddr-timing", "phandle")
    assert prop(dtb, "/dmc", "rockchip,display") == prop(dtb, "/display-subsystem", "phandle")
    assert prop(dtb, "/dmc", "center-supply") == prop(dtb, "/regulator-vdd-log", "phandle")
    assert prop(dtb, "/dmc", "operating-points-v2") == prop(dtb, "/dmc-opp-table", "phandle")
    clock = list(map(int, prop(dtb, "/dmc", "clocks").split()))
    cru = int(prop(dtb, "/clock-controller@20000000", "phandle"))
    assert clock == [cru, 2, cru, 5], clock  # PLL_DPLL, ARMCLK
    assert prop(dtb, "/regulator-vdd-log", "regulator-min-microvolt") == "1200000"
    live_opp_phandle = prop(live_dtb, "/dmc", "operating-points-v2")
    live_opp_node = None
    for child in run("fdtget", "-l", str(live_dtb), "/").splitlines():
        if "opp" in child:
            candidate = subprocess.run(["fdtget", "-t", "u", str(live_dtb), "/" + child, "phandle"],
                                       capture_output=True, text=True)
            if candidate.returncode == 0 and candidate.stdout.strip() == live_opp_phandle:
                live_opp_node = "/" + child
                break
    assert live_opp_node, "Live DMC OPP table missing"
    live_opps = {}
    for child in run("fdtget", "-l", str(live_dtb), live_opp_node).splitlines():
        node = live_opp_node + "/" + child
        cells = list(map(int, prop(live_dtb, node, "opp-hz").split()))
        hz = (cells[0] << 32) | cells[1]
        live_opps[hz] = int(prop(live_dtb, node, "opp-microvolt").split()[0])
    assert set(run("fdtget", "-l", str(dtb), "/dmc-opp-table").splitlines()) == {
        "opp-300000000", "opp-456000000"}
    for hz in (300000000, 456000000):
        node = "/dmc-opp-table/opp-" + str(hz)
        assert prop(dtb, node, "opp-hz") == "0 " + str(hz)
        volts = list(map(int, prop(dtb, node, "opp-microvolt").split()))
        assert volts[0] >= live_opps[hz] and volts[1] == 1200000 and volts[2] == 1400000

assert "of:N*T*Cpowkiddy,a12-rev-a-dmc" in run("modinfo", "-F", "alias", str(module))
assert "ARMv7" in run("modinfo", "-F", "vermagic", str(module))
parameters = run("modinfo", "-F", "parm", str(module))
assert "enable:" not in parameters and "allow_switch:" not in parameters, parameters
assert "DEVFREQ_GOV_PERFORMANCE" in driver and "DEVFREQ_GOV_USERSPACE" not in driver, "DMC must start at its highest OPP"
types = re.search(r"typedef enum\s*\{\s*SHARE_PAGE_TYPE_INVALID = 0,(.*?)\}\s*share_page_type_t;",
                  vendor_sip, re.S)[1]
assert constant(driver, "SHARE_DDR") == 1 + re.findall(r"SHARE_PAGE_TYPE_\w+", types).index("SHARE_PAGE_TYPE_DDR")
print("PASS: vendor SIP_V2 selection/layout/commands, 21 live A12 timings, display/voltage/clock links, 300/456 MHz OPPs, ARM module, enabled by default at the highest OPP")
