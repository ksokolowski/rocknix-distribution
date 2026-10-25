# Focused Mesa tiling benchmark

`mesa-tiling-bench.c` includes the configured Mesa source's `pan_tiling.c`
directly, retaining its license notices and implementation. It exercises the
aligned and generic inner kernels using uncompressed format descriptors.
An independent bit-by-bit U-interleave oracle checks both directions,
padded strides, offsets crossing tile boundaries, untouched bytes and buffer
guards. It covers 8/16/24/32/48/64/96/128-bit pixels and the depth/stencil
aspects of 32-bit pixels. Compressed formats, tiled-to-tiled copies and the
outer public-API dispatch are outside this test's scope.

The optional iteration count measures loads and stores at 16 and 32 bits,
with 384×224, 512×256 and 1024×592 images, three repetitions after warmup.
The last shape measures the full-tile portion of a 1024×600 image; the bottom
eight rows are excluded. Each timed call retains runtime format dispatch.
Results are JSON lines. Payload throughput counts one image's bytes per
call, rather than total bus traffic.

Build against an already configured Mesa source directory:

```sh
python3 projects/ROCKNIX/devices/RK3128/tools/mesa-tiling-build.py \
  build.ROCKNIX-RK3128.arm/build/mesa-<revision> \
  target/a12-diagnostics/mesa-tiling/host-bench --host --sanitize
ASAN_OPTIONS=detect_leaks=0 target/a12-diagnostics/mesa-tiling/host-bench
```

LeakSanitizer cannot run under this workspace's tracing sandbox; ASan and
UBSan remain enabled. For the A12 executable, run the builder in the normal
ROCKNIX container at `/work`, omitting `--host --sanitize`. It reuses the
actual tiler's command from `compile_commands.json`, including Cortex-A7
tuning and release settings. `--build-dir` overrides the default
`.armv7ve-rocknix-linux-gnueabi` directory. The binary's adjacent JSON file
records compiler arguments and SHA256 hashes of the benchmark, Mesa tiler,
header and binary.

Run the A12 executable without arguments for correctness only, or with
`100` for correctness plus timing. These kernels access ordinary cached
userspace buffers. They exclude GPU work, DRM buffer mapping, resource
synchronization, staging copies and presentation; their timings cannot
establish a gameplay improvement.

Always include both RetroArch and Olduvai in the subsequent same-device
comparison. Olduvai needs matching Classic/HD replays, installed fonts and
the same audio selection. Fix panel mode and governors, alternate candidate
order, preserve player settings and restore the frontend after testing.
Distinguish silent throughput from pacing, audible playback and visual
validation. Mesa's existing `LIMA_DEBUG=notiling` is one reversible
per-process candidate; source inspection confirms its spelling in
`lima_screen.c` and its resource-layout selection in `lima_resource.c`.
It affects more than the CPU tiler, so any difference is a whole-layout
comparison, rather than an isolated measurement of tiling cost.
