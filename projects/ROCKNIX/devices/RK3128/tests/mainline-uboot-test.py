#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check A12 DT/config, board hooks, clocks and miniloader image format."""

import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import re


def run(*args):
    return subprocess.check_output([str(a) for a in args], text=True, timeout=30).strip()


def source_root(build):
    return build if (build / "drivers/clk/rockchip/clk_rk3128.c").exists() else (build / "source").resolve()


def function(code, name):
    start = re.search(r"^static (?:ulong|int|void) " + name + r"\(", code, re.M).start()
    body = code.index("{", start)
    depth = 1
    end = body + 1
    while depth:
        depth += (code[end] == "{") - (code[end] == "}")
        end += 1
    return code[start:end]


def check_hooks(source):
    # Compile the actual board code with ARM32-sized data and mocked DM APIs.
    # This exercises the memory exclusion and power-enable error paths.
    with tempfile.TemporaryDirectory(prefix="a12-uboot-hooks-") as directory:
        temp = Path(directory)
        (temp / "stub.h").write_text("""
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#define CFG_SYS_SDRAM_BASE 0x60000000U
#define SZ_256M 0x10000000U
#define EINVAL 22
#define EALREADY 114
#define GD_FLG_RELOC 1
#define MMU_SECTION_SHIFT 20
#define MMU_SECTION_SIZE (1U << MMU_SECTION_SHIFT)
#define DCACHE_DEFAULT_OPTION 14
#define DECLARE_GLOBAL_DATA_PTR extern struct global_data *gd
#define log_err(...) fprintf(stderr, __VA_ARGS__)
typedef uint32_t phys_addr_t;
struct bd_info { struct { uint32_t start, size; } bi_dram[2]; };
struct global_data { uint32_t ram_size, flags; struct bd_info *bd; };
struct udevice { int unused; };
int regulator_get_by_platname(const char *, struct udevice **);
int regulator_set_enable(struct udevice *, bool);
void set_section_dcache(unsigned int, unsigned int);
""")
        for name in ("config.h", "dm.h", "log.h", "asm/global_data.h",
                     "asm/u-boot.h", "asm/cache.h", "asm/system.h", "linux/errno.h", "linux/sizes.h",
                     "power/regulator.h"):
            header = temp / name
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text('#include "stub.h"\n')
        (temp / "test.c").write_text("""
#include "stub.h"
#include <assert.h>
#include <string.h>
struct global_data data;
struct global_data *gd = &data;
static struct udevice device;
static int lookup_result, enable_result, enable_calls;
static bool executable[4096];
int rockchip_dram_init_banksize_fixup(struct bd_info *);
int rk_board_late_init(void);
void dram_bank_mmu_setup(int);
void set_section_dcache(unsigned int section, unsigned int option)
{
    assert(section < 4096 && option == DCACHE_DEFAULT_OPTION);
    executable[section] = true;
}
int regulator_get_by_platname(const char *name, struct udevice **dev)
{
    assert(!strcmp(name, "pm-enable"));
    *dev = &device;
    return lookup_result;
}
int regulator_set_enable(struct udevice *dev, bool enable)
{
    assert(dev == &device && enable);
    ++enable_calls;
    return enable_result;
}
int main(void)
{
    struct bd_info bd = {0}, before;
    data.ram_size = SZ_256M;
    assert(!rockchip_dram_init_banksize_fixup(&bd));
    assert(bd.bi_dram[0].start == 0x60000000);
    assert(bd.bi_dram[0].size == 0x08400000);
    assert(bd.bi_dram[1].start == 0x69210000);
    assert(bd.bi_dram[1].size == 0x06df0000);
    before = bd;
    dram_bank_mmu_setup(0);
    dram_bank_mmu_setup(1);
    for (unsigned int i = 0; i < 4096; ++i)
        assert(!executable[i]);
    data.flags = GD_FLG_RELOC;
    data.bd = &bd;
    dram_bank_mmu_setup(0);
    dram_bank_mmu_setup(1);
    for (unsigned int i = 0; i < 4096; ++i)
        assert(executable[i] == ((i >= 0x600 && i < 0x684) ||
                                 (i >= 0x693 && i < 0x700)));
    assert(executable[0x6ff]);
    assert(!executable[0x692]);
    const uint32_t unsupported[] = {0, 0x08000000, 0x20000000, UINT32_MAX};
    for (unsigned int i = 0; i < sizeof(unsupported) / sizeof(*unsupported); ++i) {
        data.ram_size = unsupported[i];
        assert(rockchip_dram_init_banksize_fixup(&bd) == -EINVAL);
        assert(!memcmp(&bd, &before, sizeof(bd)));
    }
    lookup_result = -19;
    assert(rk_board_late_init() == -19 && enable_calls == 0);
    lookup_result = 0;
    enable_result = -5;
    assert(rk_board_late_init() == -5 && enable_calls == 1);
    enable_result = 0;
    assert(!rk_board_late_init() && enable_calls == 2);
    enable_result = -EALREADY;
    assert(!rk_board_late_init() && enable_calls == 3);
}
""")
        run("cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", temp,
            source, temp / "test.c", "-o", temp / "test")
        run(temp / "test")


def check_artifacts(build, rkbin):
    dtb = build / "dts/dt.dtb"

    def prop(node, name, kind="x"):
        return run("fdtget", "-t" + kind, dtb, node, name).split()

    assert prop("/", "model", "s") == ["Powkiddy", "A12", "revision", "A"]
    assert prop("/aliases", "mmc0", "s") == ["/mmc@10214000"]
    assert prop("/memory@60000000", "reg") == ["60000000", "10000000"]
    assert prop("/dmc@20004000", "reg") == ["20004000", "1000"]
    assert prop("/mmc@10214000", "max-frequency", "u") == ["37500000"]
    assert prop("/mmc@10214000", "bus-width", "u") == ["4"]
    assert prop("/mmc@10214000", "status", "s") == ["okay"]
    assert "fifo-mode" in run("fdtget", "-p", dtb, "/mmc@10214000").split()
    assert prop("/mmc@1021c000", "status", "s") == ["disabled"]
    uart_pins = prop("/pinctrl/uart0/uart0-xfer", "phandle")
    assert prop("/serial@20060000", "pinctrl-0") == uart_pins
    assert prop("/serial@20060000", "clock-frequency", "u") == ["24000000"]
    assert "bootph-all" in run("fdtget", "-p", dtb, "/serial@20060000").split()
    power_pins = prop("/pinctrl/a12/pm-enable", "rockchip,pins")
    assert power_pins[:3] == ["2", "1d", "0"]
    gpio = prop("/pinctrl/gpio@20084000", "phandle")
    assert prop("/regulator-pm-enable", "gpio") == gpio + ["1d", "0"]
    assert "enable-active-high" in run("fdtget", "-p", dtb,
                                       "/regulator-pm-enable").split()

    config = (build / ".config").read_text().splitlines()
    for item in ("CONFIG_TARGET_POWKIDDY_A12_RK3128=y", "CONFIG_NR_DRAM_BANKS=2",
                 "CONFIG_SYS_MALLOC_F_LEN=0x38000",
                 "CONFIG_BOOTDELAY=0", "CONFIG_BOOTMETH_EXTLINUX=y",
                 "CONFIG_CMD_BOOTZ=y", "CONFIG_DOS_PARTITION=y",
                 "CONFIG_ENV_IS_NOWHERE=y", "# CONFIG_ENV_IS_IN_MMC is not set",
                 "# CONFIG_EFI_LOADER is not set", "# CONFIG_NET is not set"):
        assert item in config, item
    assert "CONFIG_ARMV7_NONSEC=y" not in config
    assert "CONFIG_SPL=y" not in config
    assert b"boot_targets=mmc0\0" in (build / "u-boot-nodtb.bin").read_bytes()

    image = (build / "uboot.img").read_bytes()
    payload = (build / "u-boot-dtb.bin").read_bytes()
    assert len(image) == 4 * 1024 * 1024
    assert image[:8] == b"LOADER  "
    load, size = struct.unpack_from("<II", image, 16)
    assert load == 0x60000000 and size == ((len(payload) + 3) & ~3)
    assert size + 2048 <= 1024 * 1024
    assert image[2048:2048 + len(payload)] == payload
    assert payload.endswith(dtb.read_bytes())
    for start in range(0, len(image), 1024 * 1024):
        assert image[start:start + 1024 * 1024] == image[:1024 * 1024]
    with tempfile.TemporaryDirectory(prefix="a12-uboot-pack-") as directory:
        repacked = Path(directory) / "uboot.img"
        run(rkbin / "tools/loaderimage", "--pack", "--uboot",
            build / "u-boot-dtb.bin", repacked, "0x60000000", "--size", "1024", "4")
        assert repacked.read_bytes() == image
    # Verified firmware images from the working vendor configuration.
    expected = {
        "idbloader.img": "02122958b71ff8c3ac342878df61785d1b11dce981d619258c2233deb54a90cf",
        "trust.img": "838ed48e715bd9445b24c799048a841a0263036fe88249f41f2da1abb5a1daeb",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((build / name).read_bytes()).hexdigest() == digest, name
    print("A12 mainline U-Boot artifact checks passed:", hashlib.sha256(image).hexdigest())


def check_clock_dispatch(build):
    # O= builds keep the driver's source in the separate source directory.
    root = source_root(build)
    source = root / "drivers/clk/rockchip/clk_rk3128.c"
    code = source.read_text()

    # Exercise the actual get/set dispatch with MMIO helpers mocked out.
    # The first mainline candidate rejected SCLK_SDMMC before reaching MMIO.
    header = root / "dts/upstream/include/dt-bindings/clock/rk3128-cru.h"
    harness = f'#include "{header}"\n' + """
#include <assert.h>
#include <errno.h>
typedef unsigned long ulong;
struct rk3128_clk_priv { void *cru; };
struct clk { void *dev; unsigned int id; };
#define dev_get_priv(dev) ((struct rk3128_clk_priv *)(dev))
#define CLK_GENERAL 4
#define rk3128_peri_get_pclk(...) 0UL
#define rk3128_saradc_get_clk(...) 0UL
#define rk3128_vop_get_rate(...) 0UL
#define rk3128_vop_set_clk(...) 0UL
#define rk3128_peri_set_pclk(...) 0UL
#define rk3128_saradc_set_clk(...) 0UL
static int queries, requests;
static ulong rkclk_pll_get_rate(void *cru, unsigned int id)
{
    assert(cru && id == CLK_GENERAL);
    return 594000000;
}
static ulong rockchip_mmc_get_clk(void *cru, unsigned int parent, unsigned int id)
{
    assert(cru && parent == 594000000);
    assert(id == SCLK_SDMMC || id == HCLK_SDMMC);
    ++queries;
    return 74250000;
}
static ulong rockchip_mmc_set_clk(void *cru, unsigned int parent,
                                 unsigned int id, unsigned int rate)
{
    assert(cru && parent == 594000000);
    assert(id == SCLK_SDMMC || id == HCLK_SDMMC);
    assert(rate == 37500000 || rate == 400000);
    ++requests;
    return rate;
}
""" + function(code, "rk3128_clk_get_rate") + "\n" + function(code, "rk3128_clk_set_rate") + """
int main(void)
{
    struct rk3128_clk_priv priv = { &priv };
    struct clk clk = { &priv, SCLK_SDMMC };
    assert(rk3128_clk_set_rate(&clk, 400000) == 400000);
    assert(rk3128_clk_set_rate(&clk, 37500000) == 37500000);
    assert(rk3128_clk_get_rate(&clk) == 74250000);
    clk.id = HCLK_SDMMC;
    assert(rk3128_clk_set_rate(&clk, 400000) == 400000);
    assert(rk3128_clk_get_rate(&clk) == 74250000);
    assert(requests == 3 && queries == 2);
    clk.id = SCLK_UART0;
    assert(rk3128_clk_get_rate(&clk) == (ulong)-ENOENT);
}
"""
    with tempfile.TemporaryDirectory(prefix="a12-uboot-clock-") as directory:
        temp = Path(directory)
        (temp / "test.c").write_text(harness)
        run("cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            temp / "test.c", "-o", temp / "test")
        run(temp / "test")
    print("RK3128 SD clock dispatch checks passed")


def check_pll_lock(build):
    root = source_root(build)
    code = (root / "drivers/clk/rockchip/clk_rk3128.c").read_text()
    # Compile the real PLL programming, clock initialization/probe and VOP
    # functions against real register definitions, replacing only MMIO/DM.
    with tempfile.TemporaryDirectory(prefix="a12-uboot-pll-") as directory:
        temp = Path(directory)
        (temp / "linux").mkdir()
        (temp / "linux/bitops.h").write_text("""
#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((~0U << (l)) & (~0U >> (31 - (h))))
""")
        harness = """
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned int uint;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned long ulong;
#define debug(...) do {} while (0)
#define check_member(...) /* register offsets covered by the ARM build */
""" + f'#include "{root}/arch/arm/include/asm/arch-rockchip/cru_rk3128.h"\n'
        harness += f'#include "{root}/dts/upstream/include/dt-bindings/clock/rk3128-cru.h"\n'
        harness += """
enum rk_clk_id { CLK_ARM = 1, CLK_DDR, CLK_CODEC, CLK_GENERAL };
static int rk_pll_id(enum rk_clk_id id) { return id - 1; }
static struct rk3128_cru cru;
static int reads[4], lock_after[4], delays;
static uint readl(const uint *address)
{
    for (int i = 0; i < 4; ++i)
        if (address == &cru.pll[i].con1) {
            ++reads[i];
            return (*address & ~PLL_LOCK_STATUS_MASK) |
                (reads[i] > lock_after[i] ? PLL_LOCK_STATUS_MASK : 0);
        }
    return *address;
}
static void udelay(uint delay)
{
    assert(delay == 1);
    assert(++delays <= 1000);
}
static void rk_clrsetreg(uint *address, uint clear, uint set)
{
    *address = (*address & ~clear) | set;
}
#define rk_setreg(address, set) rk_clrsetreg(address, 0, set)
#define rk_clrreg(address, clear) rk_clrsetreg(address, clear, 0)
#define ilog2(value) (31 - __builtin_clz((unsigned int)(value)))
struct udevice { struct rk3128_clk_priv *priv; };
#define dev_get_priv(dev) ((dev)->priv)
static void reset(void)
{
    memset(&cru, 0, sizeof(cru));
    memset(reads, 0, sizeof(reads));
    memset(lock_after, 0, sizeof(lock_after));
    delays = 0;
}
"""
        harness += code[code.index("enum {"):code.index("static int rkclk_set_pll(")]
        harness += function(code, "rkclk_set_pll") + "\n"
        harness += function(code, "rkclk_init") + "\n"
        harness += function(code, "rk3128_clk_probe") + "\n"
        harness += """
static int pll_para_config(u32 hz, struct pll_div *div)
{
    assert(hz == 74250000);
    *div = gpll_init_cfg;
    return 0;
}
""" + function(code, "rk3128_vop_set_clk") + "\n" + """
int main(void)
{
    struct rk3128_clk_priv priv = { &cru };
    struct udevice dev = { &priv };
    reset();
    assert(!rkclk_set_pll(&cru, CLK_ARM, &apll_init_cfg));
    assert(reads[0] == 1 && delays == 0);
    reset();
    lock_after[0] = 5;
    assert(!rkclk_set_pll(&cru, CLK_ARM, &apll_init_cfg));
    assert(reads[0] == 6 && delays == 5);
    reset();
    lock_after[0] = 1000;
    assert(!rkclk_set_pll(&cru, CLK_ARM, &apll_init_cfg));
    assert(reads[0] == 1001 && delays == 1000);
    reset();
    lock_after[0] = 1001;
    assert(rkclk_set_pll(&cru, CLK_ARM, &apll_init_cfg) == -ETIMEDOUT);
    assert(reads[0] == 1001 && delays == 1000);
    reset();
    assert(!rk3128_clk_probe(&dev));
    assert((cru.cru_mode_con & (APLL_MODE_MASK | GPLL_MODE_MASK)) ==
           ((APLL_MODE_NORM << APLL_MODE_SHIFT) | (GPLL_MODE_NORM << GPLL_MODE_SHIFT)));
    assert(reads[0] == 1 && reads[3] == 1);
    reset();
    lock_after[0] = 10000;
    assert(rk3128_clk_probe(&dev) == -ETIMEDOUT);
    assert(reads[3] == 0 && cru.cru_mode_con == 0 && cru.cru_clksel_con[0] == 0);
    reset();
    lock_after[3] = 10000;
    assert(rk3128_clk_probe(&dev) == -ETIMEDOUT);
    assert(cru.cru_mode_con == 0 && cru.cru_clksel_con[0] == 0);
    reset();
    lock_after[2] = 10000;
    cru.cru_clksel_con[27] = 0x1234;
    assert(rk3128_vop_set_clk(&cru, DCLK_VOP, 74250000) == (ulong)-ETIMEDOUT);
    assert(cru.cru_clksel_con[27] == 0x1234);
    reset();
    assert(rk3128_vop_set_clk(&cru, DCLK_VOP, 74250000) == 74250000);
}
"""
        (temp / "test.c").write_text(harness)
        run("cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-I", temp,
            temp / "test.c", "-o", temp / "test")
        subprocess.run([str(temp / "test")], check=True, timeout=5)
    print("RK3128 PLL lock, timeout and error propagation checks passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path, help="built official U-Boot source directory")
    parser.add_argument("rkbin", type=Path, help="pinned rk3128-blobs source directory")
    args = parser.parse_args()
    board = Path(__file__).resolve().parent.parent / "packages/u-boot/sources/board/powkiddy/a12-rk3128/a12-rk3128.c"
    check_hooks(board)
    check_pll_lock(args.build.resolve())
    check_artifacts(args.build.resolve(), args.rkbin.resolve())
    check_clock_dispatch(args.build.resolve())
