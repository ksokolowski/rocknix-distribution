# Powkiddy A12 (revision A)

A ROCKNIX target for the Powkiddy A12 mini bartop cabinet, revision A:
Rockchip RK3128 (quad Cortex-A7 at 1.2 GHz, Mali-400 MP2), 256 MiB RAM and
a 1024×600 RGB panel. It is a native 32-bit ARM build (`ARCH=arm`), the only
one in ROCKNIX, with a mainline kernel and mainline U-Boot.

The Powkiddy A13 is the same board in a different case and runs the same
image, Linux 7.3 included; its DDR passed a memtester run at 456 MHz.

This is a personal port. It works on the owner's devices, but it is not an
official ROCKNIX device. Flash it to a spare SD card and keep the stock or
KNULLI card for recovery.

## Build

In the ROCKNIX build container (`make docker-shell`):

```sh
make RK3128                                                  # image and update tar in target/
PROJECT=ROCKNIX DEVICE=RK3128 ARCH=arm ./scripts/build <pkg>   # one package
```

`NATIVE_ARM=yes` in `options` makes `ARCH=arm` a full image with its
libraries in `/usr/lib`, instead of the 32-bit compatibility layer that other
devices build for their 64-bit images.

## What works

Verified on the A12 revision A:

| Area | Implementation |
| --- | --- |
| Boot | Mainline U-Boot 2026.07 with a revision A board target and RK3128 clock and QoS fixes (`packages/u-boot`), pinned rkbin loader and TEE. Cold boots and warm reboots both work. |
| Kernel | Mainline Linux 7.3 (shared `linux` package), A12 config `linux/linux.arm.conf`, board tree `rk3128-powkiddy-a12-rev-a.dts`, patches in `patches/linux/` |
| Display | Out-of-tree panel and TTL video PHY drivers. 60 Hz by default (`panel_a12.refresh_60hz=0` selects the native ~85 Hz mode). Boot splash with progress over KMS. |
| Graphics | Lima, GLES2, no display server (SDL and RetroArch on KMS/DRM) |
| Memory | DDR switched from 300 to 456 MHz at boot (out-of-tree DMC driver using the TEE's SIP interface), 256 MiB zram (lzo-rle, zstd recompression), watermark boosting off, LZ4 SquashFS |
| Controls | GPIO buttons, ES and RetroArch mappings by button label, volume keys, Select or Back + volume for brightness, game exit hotkeys (`a12-controls`). USB pads: xpad (Xbox), hid-playstation and hid-nintendo drivers |
| Audio | RK312x codec (out-of-tree driver), ALSA only with dmix and a softvol `Master`, no PipeWire |
| Battery | ADC voltage and charge state (out-of-tree driver) |
| Network | USB Ethernet (RTL8156) and USB Wi-Fi (RTL8188EU, with a radio restart fix) |
| USB | Bottom USB-A: EHCI/OHCI host. Top USB-A: DWC2 OTG forced to host (no ID pin). USB-C: charging (no data use found). Keyboard and mouse work (USB HID): in ES, and as a real keyboard in the computer cores (Amiga, C64, MSX, ZX Spectrum, Amstrad, DOS) and ScummVM |
| Power | The screen darkens after the ES screensaver time (5 min by default) or 15 min in a game; one press wakes it. On battery the backlight keeps its own level (40 % at first). Clean shutdown at 5 % battery. ES menu on `schedutil`, games on `performance`. A POWER SAVING switch in ES system settings turns the policy off. |
| Frontend | EmulationStation with a reduced core set for 256 MiB; ES lists only the cores the image contains (`ES_ONLY_BUILT_CORES`). VLC built only for ES previews and thumbnails. |

The board has no internal Wi-Fi or Bluetooth. Suspend is disabled until a
wake source is verified.

## Cores

NES (FCEUmm, Nestopia, QuickNES), SNES (Snes9x 2002/2005 Plus/2010), Game
Boy/Color (Gambatte, Gearboy), GBA (gpSP, mGBA), Master System and Game Gear
(Gearsystem, Genesis Plus GX, PicoDrive), Mega Drive (Genesis Plus GX,
PicoDrive), PC Engine (Beetle PCE Fast), PlayStation (PCSX ReARMed), arcade
(FBNeo, FB Alpha 2012, MAME 2003-Plus), Atari 2600/7800/Lynx (Stella,
ProSystem, Handy), Neo Geo Pocket, WonderSwan, Virtual Boy (Beetle), Pokémon
Mini, Intellivision, Vectrex, Atari 800/5200 (atari800, a5200), Odyssey2 (O2EM),
PICO-8 (FAKE-08), TIC-80, WASM-4, ZX Spectrum, Amstrad CPC, MSX (blueMSX), C64
(VICE x64sc), Amiga (uae4arm), DOS (DOSBox Pure), Doom (PrBoom), Game & Watch,
ScummVM and Moonlight (see known issues). The list is in
`projects/ROCKNIX/packages/virtual/emulators/package.mk`.

beetle_vb carries speed patches for the Cortex-A7 (`patches/beetle-vb-lr/`,
bit-identical output): Virtual Boy Wario Land runs at 134 instead of 56 FPS
headless on the A13.

ScummVM 2026.4.0 scales 320x200 games 3x with xBRF, an xBR-family pixel-art
scaler, on the CPU (`patches/scummvm-sa/0002`): it works on the changed
rectangles only, spread over the four cores. Wider games stay at 1x.
Music picks the best device per game: Roland MT-32 when `MT32_CONTROL.ROM`
and `MT32_PCM.ROM` are in `roms/bios` (not included), FluidSynth for General
MIDI games (single precision with NEON, samples loaded on demand), AdLib
otherwise. Output runs at 48 kHz, the mixer's rate.

## Known issues

- Updating applies slowly: the first boot after an update can show only
  the logo for about three minutes while it rebuilds the hardware database.
- USB Wi-Fi can drop after EmulationStation restarts; wired USB Ethernet is
  the reliable link.
- Unplugging the charger and a USB adapter together while on battery can
  reset the board (supply dip).
- Moonlight does not start: its library needs Rockchip MPP, which the
  image does not include.
- Headphone switching and every button have not been rechecked on Linux 7.3.

## Layout

- `options`: toolchain, graphics, audio, zram and image settings.
- `linux/`, `patches/linux/`: kernel config, device tree and kernel patches.
- `packages/rk3128-hardware/`: out-of-tree drivers (panel, TTL PHY, battery,
  codec, DMC), adapted from the KNULLI vendor kernel with Rockchip's GPL
  notices kept.
- `packages/a12-controls/`: input daemon, splash, diagnostics, game monitor
  and the RetroArch launcher wrapper.
- `packages/u-boot/`, `packages/rk3128-blobs/`, `bootloader/`: bootloader,
  pinned firmware and image layout. `packages/u-boot/README.md` has the port
  notes and a QEMU harness for the boot path.
- `packages/` also holds device overrides of shared packages, and
  `packages/quirks/` systemd drop-ins. Shared code gated by `DEVICE` or
  `HW_DEVICE`: grep for `RK3128`.
- `patches/`: patches for other packages (beetle-vb, FBNeo, Mesa, VLC,
  RetroArch, SDL2, EmulationStation, …).
- `tests/`: host-side tests, `tests/run-all.sh` runs all of them. With
  `arm-linux-gnueabihf-gcc` and `qemu-arm` installed it also runs the C tests
  as ARM binaries; with `arm-linux-gnueabihf-g++` too, `vb-anaglyph-test.py`
  compares ARM NEON builds of beetle_vb (needs `A12_VB_ROMS`).
- `tools/`: deployment, diagnostics and benchmark tools (`tools/bench/`).

Comments and tests refer to numbered hardware tests ("test 72"). Those
come from the owner's test log, which is not part of this tree.

## Boot and DTB

The full revision A tree is loaded through extlinux (`FDT
/device_trees/rk3128-powkiddy-a12-rev-a.dtb`); there are no overlays. A fresh
image writes the loader, TEE and U-Boot at their raw offsets. An update
replaces the kernel, system and DTB and keeps the raw bootloader and
extlinux configuration (`bootloader/update.sh`).

## Diagnostics

`a12-hardware-report` (over SSH) collects driver, battery, display, audio,
input, memory and storage state. A diagnostics timer saves a report 45 s
after boot and at shutdown to `/storage/.cache/a12-diagnostics/`, and the
next boot keeps the previous one in `prev/`. Kernel crashes go to ramoops and
are archived on the next boot.
