# A12 revision A mainline U-Boot

The package builds official `u-boot/u-boot` commit
`ece349ade2973e220f524ce59e59711cc919263f` (v2026.07), checked against the
official master branch on 2026-10-09. The commit and archive SHA256 are
pinned in `package.mk`. The candidate compiles with ROCKNIX GCC 16.2.0 and
binutils 2.47.20260726. The first three hardware candidates fail to boot.
Packaged QEMU now reproduces
two additional boot-stopping faults; the corrected GCC 13 candidate reaches
Linux entry with the card's exact boot files in emulation. On 2026-10-10 the
owner confirms this fourth candidate boots on A12 revision A. In the resumed
session the normal GCC 16 build also boots, with the owner reporting quick
screen activation without a timed measurement. SSH captures the expected
TEE-excluding Linux memory map, and a read-only raw-device hash confirms
the installed GCC 16 image. A full peripheral regression and repeated
cold boots remain pending.

## Board support and provenance

`sources/` supplies a dedicated `powkiddy-a12-rk3128_defconfig`, board hooks
and a minimal revision A device tree. The Kconfig patch registers the
target. RK3128 clock, pinctrl, serial, RAM and MMC drivers come from official
U-Boot, with SD clock dispatch and PLL lock corrections in the second and
third patches. Patches 0004 and 0005 port vendor caesar-u-boot 9724e7aa
settings that Linux inherits from the bootloader: 0004 programs GPLL
(VCO 2376 MHz) and CPLL (400 MHz) like the vendor `rkclk_init`; 0005 adds
the LCDC QoS priority 3/3 from the vendor RK3128 `arch_cpu_init`. Without it
the LCDC kept priority 1/1 and the RGB panel showed black vertical lines
under memory load (TEST_LOG tests 30--33). The vendor function's other two
writes are not ported: the MSCH read latency is already 0x3f before U-Boot,
and muxing GPIO1C1 (sdcard_detn) to GPIO stops a cold power-on of the A12
while warm reboots still work (tests 37--38). Validate every bootloader
change with a cold power-on from off, not only `reboot`.
No RK3326 configuration is reused.

SD and UART assignments come from working revision A captures and the
ROCKNIX Linux tree. The owner's local `knulli-linux` recipes under
`board/rockchip/rk3128/powkiddy_a13/` and packages `uboot-powkiddy-a13` and
`rk3128-blobs` were inspected alongside the local `knulli-kernel` WX8 tree
and history. Revision C/D trees are comparison references only. GPIO2_D5
power enable is confirmed in the working revision A capture and vendor
`board/rockchip/wx8_rk3128/wx8-rk3128.c` at caesar commit
`9724e7aac8f99c2b9cb225b8cb12590153440cb4`. A fixed regulator enables this
GPIO through mainline DM/pinctrl; UART0 uses TX/RX only so CTS cannot take it.

The DRAM bank hook uses mainline Rockchip's existing fixup interface and
retains its GPL notice. It excludes `0x68400000–0x69210000`, the trusted
firmware region verified in the running revision A memory map. It rejects
any detected capacity other than 256 MiB. This exclusion is tied to the
pinned TEE blob below; firmware changes require revalidating the layout.

The first candidate failed to boot (owner observation, no UART available).
The modern MMC driver requests `SCLK_SDMMC`, which the RK3128 clock
dispatch rejected with `-ENOENT` despite an existing SD rate helper.
The corrected port dispatches SD clock queries/requests to that helper.
An earlier claim that UART0 lacked its baud clock was incorrect: the first
compiled DTB already inherited upstream's 24 MHz `clock-frequency`.
Making that property explicit is redundant; `bootph-all` allows early
binding. Early allocation space is raised
from the inherited 2 KiB to the working vendor target's 224 KiB; no measured
heap exhaustion is claimed without a boot trace.

The second candidate (`2171c0b7…`, GCC 13.3) also fails to boot. Inspection
then finds the RK3128 PLL poll waiting while LOCK is set, contrary to the
[Rockchip RK312X TRM, section 3.9.2](https://rockchip.fr/RK312X%20TRM/chapter-03-clock-and-reset-unit.pdf).
The working vendor implementation in caesar-u-boot `9724e7aa`,
`drivers/clk/rockchip/clk_pll.c`, waits for a set bit. The third patch fixes
the polarity, bounds the wait to 1 ms and propagates timeout errors through
clock initialization/probe and the VOP clock setter. It does not establish
where either failed hardware run stopped. Both vendor and mainline skip
low-level CPU initialization; that configuration is not a measured gap.

The U-Boot-only DT include also corrects the inherited RK3128 DMC `reg` property
to match the SoC's one address cell and one size cell. SD reads use PIO at
up to 37.5 MHz for the initial candidate. The Linux DTB remains the full
existing revision A tree selected by extlinux.

## Firmware and disk layout

Keep working rkbin revision `7d631e0d5b2d373b54d4533580d08fb9bd2eaad4`:

- DDR: `rk3128_ddr_300MHz_v2.12.bin`.
- Miniloader: `rk3128x_miniloader_v2.57.bin`.
- Trusted firmware: `rk3126_tee_ta_v2.01.bin`.

These blobs retain their separate nonfree license. Official `tools/mkimage`
creates the SD loader header. Pinned rkbin `tools/loaderimage` packs
`u-boot-dtb.bin` into four 1 MiB copies with the legacy `LOADER` header and
load address `0x60000000`. There is no native SPL in this configuration.
The loader tool prints its own embedded 2017.09 version string; the compiled
payload's generated version header identifies U-Boot 2026.07.

The resulting `idbloader.img` and `trust.img` match verified vendor images
byte for byte; their SHA256 values are checked by the artifact test. Image
creation retains sector 64 for idbloader, sector 16384 for the 4 MiB U-Boot
region and sector 24576 for the 4 MiB trust region.

Boot uses SD/extlinux and `bootz`. Persistent environment storage is
disabled, so no old MMC environment at offset zero is imported or saved.
U-Boot preserves CPU security mode and the resident secure monitor at the
Linux handoff, matching the working vendor's secure-default boot behavior.
The first candidate does not initialize the display; the existing Linux
splash remains available after the kernel starts.

## Validation and hardware tests

Build inside the ROCKNIX container:

```sh
PROJECT=ROCKNIX DEVICE=RK3128 ARCH=arm ./scripts/build u-boot
```

On the host, with `cc` and `fdtget` available:

```sh
python3 projects/ROCKNIX/devices/RK3128/tests/mainline-uboot-test.py \
  build.ROCKNIX-RK3128.arm/build/u-boot-ece349ade2973e220f524ce59e59711cc919263f \
  build.ROCKNIX-RK3128.arm/build/rk3128-blobs-7d631e0d5b2d373b54d4533580d08fb9bd2eaad4
```

The test compiles actual board hooks with ARM32-sized mock data and checks
the TEE hole, capacity rejection, complete MMU section coverage,
`-EALREADY` handling and genuine regulator error propagation. It also
checks compiled DT/configuration, payload/load address, four identical
copies, deterministic repacking and unchanged firmware. The actual clock
dispatch functions are compiled with mocked MMIO helpers to check that SD
requests reach the helper. Actual PLL programming, clock initialization,
probe and VOP functions are compiled against the real register definitions
to check immediate/delayed lock, the timeout boundary and error propagation.
Restoring the original poll condition makes the regression fail. Passing these
checks establishes build and packaging validity, not boot.

For the first hardware test, use the host SD reader to back up and verify
working Stage B, then replace only the 4 MiB U-Boot region at offset 8 MiB.
Verify uncached readback and adjacent bytes. Preserve the filesystems,
kernel, Linux DTB, extlinux, idbloader and trust. Device networking is
unnecessary for this swap or observing a boot. Recovered Stage B SHA256:
`a45cfb6d2de55ae9c0f4e74041539ca47b6bba01781353b7648e9a305f74bef2`.

After boot, confirm display, controls, audio, storage and shutdown. Saved
Linux memory reports should still show banks `0x60000000/0x08400000` and
`0x69210000/0x06df0000`. Collect them over SSH if convenient, or from STORAGE
after returning the card to the reader. Raw bootloader updates remain
outside the normal OS update script. Every source update needs another
hardware boot test before being called working.

The corrected port builds with both ROCKNIX GCC 16.2/binutils 2.47 and the
existing KNULLI GCC 13.3/binutils 2.42 toolchain. The failed PLL-corrected
third candidate is `fe33d1f3…`; the new fourth candidate uses GCC 13 and
only changes the two board hooks below. Its configuration and compiled
U-Boot DTB are byte-identical to the third candidate.

| Corrected toolchain | Packed U-Boot image SHA256 |
| --- | --- |
| GCC 13.3 / binutils 2.42, fourth hardware candidate | `11170ddc7c34de3afd6d67de096a28da6be394ad0deac0416f9b1451b7c8a469` |
| GCC 16.2 / binutils 2.47.20260726, fifth hardware candidate, boots | `b0b1f072c64b2594f85d0c74c3f1f927a56b23ecfeb0353f4fad03827495d6b3` |

The package continues to use the normal ROCKNIX toolchain; no compiler
downgrade is adopted.

## Reproduced faults and packaged QEMU, 2026-10-10

The actual third-candidate ARM binary faults immediately after MMU activation.
Mainline's weak `dram_bank_mmu_setup()` truncates the unaligned second bank's
start and size independently. It maps sections `0x692` through `0x6fe`,
leaving section `0x6ff` execute-never (`0x6ff00c12`), despite U-Boot relocating
to `0x6ffb2000`. QEMU reaches the prefetch-abort vector at `0x6ffb200c`.
Overriding only that descriptor with `0x6ff00c0e` lets the same binary continue.
The board now overrides the MMU hook to map every complete section contained
inside each usable bank. Section `0x6ff` is executable; `0x684`–`0x692` remain
uncached and execute-never, including the TEE's final 64 KiB. Linux still gets
the precise byte-granular bank boundaries, including usable RAM at `0x69210000`.

The descriptor experiment then exposes a second fatal error: probing the
`regulator-boot-on` power GPIO already enables it. Calling
`regulator_set_enable(dev, true)` again returns `-EALREADY` (-114), and the
previous board hook treats it as fatal. The hook now accepts that already
enabled state while propagating real errors. Both changes have regression
coverage compiling the actual board source.

The reusable harness is `../../tools/a12-uboot-qemu.py`. It executes the real
ARM payload on packaged QEMU's Cortex-A7 with `-M none`, using the generic
loader and GDB remote watchpoints to model selected RK3128 registers. Stock
QEMU has no RK3128 board model. No QEMU source build or installation is used.
The recorded run uses Ubuntu's QEMU 6.2.0 package
`1:6.2+dfsg-2ubuntu6.31` in an isolated Docker container. On a suitable Debian
or Ubuntu analysis system, prerequisites can be installed as packages:

```sh
sudo apt-get install qemu-system-arm dosfstools mtools device-tree-compiler
python3 -m venv /tmp/a12-qemu-venv
/tmp/a12-qemu-venv/bin/pip install capstone==5.0.9 pyelftools==0.33
```

Set `UBOOT_BUILD` to the GCC 13 build directory, and `BOOT_FILES` to a saved
copy of the card's `KERNEL`, `device_trees/` and `extlinux/` files. The fixture
is a new synthetic disk file; no mount, root access or physical SD writing
is involved in its creation or execution:

```sh
/tmp/a12-qemu-venv/bin/python \
  projects/ROCKNIX/devices/RK3128/tools/a12-uboot-qemu.py \
  "$UBOOT_BUILD/u-boot" "$UBOOT_BUILD/u-boot-dtb.bin" \
  target/a12-qemu/run --inspect-mmu --fast-fifo \
  --sd-fixture target/a12-qemu/sd.img --create-fixture-from "$BOOT_FILES" \
  --expected-kernel "$BOOT_FILES/KERNEL" --seconds 90
fdtget -t x target/a12-qemu/run/handoff.dtb /memory reg
```

Omit `--create-fixture-from` when reusing the existing fixture. Success exits
0 only after reaching Linux entry. The report records UART, CPU milestones,
MMU descriptors, SD commands, unknown register reads, payload and fixture
hashes, and FIFO acceleration. `loaded-kernel.bin` is checked byte for byte
by SHA256 against the input kernel; `handoff.dtb` captures the actual Linux
DTB at entry. `--patch-final-bank` is an explicit diagnostic override for
reproducing the second fault, never a way to validate a corrected build.

The fourth candidate passes DRAM discovery, relocation, MMU activation,
power setup, SD discovery, FAT/extlinux, kernel/DTB loading, preparation and
the actual jump to `0x62000000`. Linux receives `r0=0`, `r1=0`,
`r2=0x683f3000`; its DTB memory property is
`60000000 08400000 69210000 06df0000`. This also passes with the exact boot
files copied from the returned card on 2026-10-10. The GCC 16 build passes
MMU, regulator and MMC initialization in a bounded unaccelerated run; its
full Linux handoff is not established by that shorter run.

This is a limited CPU/MMIO model, not complete A12 emulation. Synthetic GRF
geometry describes 256 MiB; PLL lock is immediate, UART is always ready,
and the SDHC card is a synthetic 128 MiB PIO fixture. Unknown reads default
to zero and are logged. The 2 GiB QEMU RAM scaffold backs both real DDR and
watched register addresses, so it does not catch every out-of-range RAM
access. No boot ROM, proprietary DDR/miniloader/TEE, secondary CPU, IRQ,
display, analogue timing or electrical behavior is simulated. The test
stops at Linux entry; it does not claim the kernel or peripherals boot.

`--fast-fifo` accelerates only a checked scalar GCC 13 FIFO-copy instruction
sequence by injecting the same queued words and final loop-register state;
it records each batch. The unaccelerated source-fixed run independently
passes initialization and begins reading the kernel. Full handoff and kernel
integrity use acceleration to avoid millions of debugger round trips.
No MMU or regulator override is used in corrected-build validation. The
working vendor Stage B control independently passes relocation/MMU; its
complete storage boot has not been modeled.

One additional source difference remains hardware-dependent: vendor startup
sets Cortex-A7 ACTLR.SMP before cache operations; mainline's equivalent
low-level hook is skipped in this miniloader configuration. The incoming
CPU state from the proprietary loader is unknown, and QEMU does not validate
physical cache coherency or timing. This remains a follow-up if hardware
still fails; it is not folded into the two reproduced fixes without evidence.

The [DDR investigation](../../plans/2026-10-10-a12-ddr-qemu-investigation.md)
records an earlier QEMU protocol harness for the DMC driver; it was removed
once 456 MHz ran on hardware by default.

## Display draft (B3, not verified on hardware)

`A12_UBOOT_DISPLAY=yes` builds `powkiddy-a12-display-rk3128_defconfig`: the
normal configuration plus `CONFIG_VIDEO`, the PWM backlight and
`CONFIG_A12_DISPLAY`, with `rk3128-powkiddy-a12-rev-a-display.dts` (the
normal A12 tree plus the panel, TTL PHY, `pwm0` and RGB pins from the
ROCKNIX Linux DTS). `board/powkiddy/a12-rk3128/a12-display.c` sets dclk_vop
to GPLL/11 (54 MHz, CPLL untouched), powers the TTL PHY, runs the panel-a12
power sequence and programs the RK3036-family VOP for the 60-hblank mode
with RGB666 dithering and the rising-edge clock. The default build is
unchanged: on 2026-10-11 (cloud session, Ubuntu arm-linux-gnueabihf GCC
13.3) the normal defconfig built byte-identical apart from the build time
with and without the new files, `tests/mainline-uboot-test.py` passed on
that build with the pinned rkbin, and the display variant compiled without
warnings. Before using it: a recovery card, a cold power-on test, and a
check that Linux still lights the panel after U-Boot did.
