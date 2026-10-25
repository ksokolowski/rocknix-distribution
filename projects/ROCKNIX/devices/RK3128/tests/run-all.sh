#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Run every A12 host test from the repository root; no hardware or build needed.
# Tests that need build outputs (dmc-reference, mainline-uboot) run only when
# their arguments are given in A12_DMC_REFERENCE_ARGS / A12_MAINLINE_UBOOT_ARGS.
# Exit status is the number of failed tests.

cd "$(dirname "$0")/../../../../.." || exit 1
tests=projects/ROCKNIX/devices/RK3128/tests
splash=projects/ROCKNIX/devices/RK3128/packages/a12-controls/sources/splash
work=$(mktemp -d)
trap 'rm -rf "${work}"' EXIT

failed=0
skipped=0

report() { # name status output
  case "$2" in
    0)
      if grep -q '^note: .*skipped' <<<"$3"; then
        echo "SKIP $1 ($(grep -m1 '^note:' <<<"$3" | cut -c7-))"
        skipped=$((skipped + 1))
      else
        echo "ok   $1"
      fi
      ;;
    *)
      echo "FAIL $1"
      sed 's/^/     /' <<<"$3" | tail -15
      failed=$((failed + 1))
      ;;
  esac
}

run() { # name command...
  local name=$1 out
  shift
  out=$("$@" 2>&1)
  report "${name}" $? "${out}"
}

c_test() { # name sources...
  local name=$1 out
  shift
  if out=$(gcc -Wall -Wextra -Werror -o "${work}/${name}" "$@" 2>&1); then
    out=$("${work}/${name}" 2>&1)
    report "${name}" $? "${out}"
  else
    report "${name}" 1 "${out}"
  fi
}

for test in "${tests}"/*.py; do
  name=$(basename "${test}" .py)
  case "${name}" in
    dmc-reference-test)
      if [ -n "${A12_DMC_REFERENCE_ARGS}" ]; then
        # shellcheck disable=SC2086
        run "${name}" python3 "${test}" ${A12_DMC_REFERENCE_ARGS}
      else
        echo "SKIP ${name} (needs DTB LIVE_DTS VENDOR_KERNEL MODULE in A12_DMC_REFERENCE_ARGS)"
        skipped=$((skipped + 1))
      fi
      ;;
    mainline-uboot-test)
      if [ -n "${A12_MAINLINE_UBOOT_ARGS}" ]; then
        # shellcheck disable=SC2086
        run "${name}" python3 "${test}" ${A12_MAINLINE_UBOOT_ARGS}
      else
        echo "SKIP ${name} (needs BUILD RKBIN in A12_MAINLINE_UBOOT_ARGS)"
        skipped=$((skipped + 1))
      fi
      ;;
    *)
      run "${name}" python3 "${test}"
      ;;
  esac
done

c_test controls-test "${tests}/controls-test.c"
c_test splash-draw-test "${tests}/splash-draw-test.c" "${splash}/splash-draw.c"
c_test update-splash-test "${tests}/update-splash-test.c" "${splash}/splash-draw.c" "${splash}/splash-kms.c" "${splash}/splash-fb.c"
c_test splash-progress-test "${tests}/splash-progress-test.c" "${splash}/splash-progress.c"
c_test splash-main-test "${tests}/splash-main-test.c" "${splash}/splash-fb.c"
c_test splash-sd-fixture -I "${tests}/stubs" "${tests}/splash-sd-fixture.c" "${splash}/splash-sd.c" \
  "${splash}/splash-progress.c" "${splash}/splash-draw.c" "${splash}/splash-fb.c"

# The A12 is 32-bit ARMv7: with a cross compiler and qemu-user, run the C
# tests as ARM binaries too (pointer/u64 and off_t sizes differ from x86-64).
qemu_arm=$(command -v qemu-arm-static || command -v qemu-arm || true)
if command -v arm-linux-gnueabihf-gcc >/dev/null 2>&1 && [ -n "${qemu_arm}" ]; then
  arm_test() { # name sources...
    local name=$1 out
    shift
    if out=$(arm-linux-gnueabihf-gcc -static -march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard -O2 \
        -Wall -Wextra -Werror -o "${work}/${name}" "$@" 2>&1); then
      out=$("${qemu_arm}" "${work}/${name}" 2>&1)
      report "${name}" $? "${out}"
    else
      report "${name}" 1 "${out}"
    fi
  }
  arm_test arm-controls-test "${tests}/controls-test.c"
  arm_test arm-splash-draw-test "${tests}/splash-draw-test.c" "${splash}/splash-draw.c"
  arm_test arm-splash-progress-test "${tests}/splash-progress-test.c" "${splash}/splash-progress.c"
  arm_test arm-splash-main-test "${tests}/splash-main-test.c" "${splash}/splash-fb.c"
  arm_test arm-splash-sd-fixture -I "${tests}/stubs" "${tests}/splash-sd-fixture.c" "${splash}/splash-sd.c" \
    "${splash}/splash-progress.c" "${splash}/splash-draw.c" "${splash}/splash-fb.c"
  arm_test arm-splash-kms-fixture "${tests}/splash-kms-fixture.c" "${splash}/splash-kms.c"
else
  echo "SKIP arm-* (arm-linux-gnueabihf-gcc or qemu-arm not installed)"
  skipped=$((skipped + 1))
fi

if [ -r /usr/include/drm/drm_mode.h ]; then
  c_test splash-kms-fixture "${tests}/splash-kms-fixture.c" "${splash}/splash-kms.c"
else
  echo "SKIP splash-kms-fixture (kernel UAPI headers not installed)"
  skipped=$((skipped + 1))
fi

font=/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf
if pkg-config --exists freetype2 2>/dev/null && [ -r "${font}" ]; then
  # shellcheck disable=SC2046
  if out=$(gcc -Wall -Wextra -Werror -DSPLASH_TTF $(pkg-config --cflags freetype2) \
      -o "${work}/splash-ttf-test" "${tests}/splash-ttf-test.c" "${splash}/splash-draw.c" \
      "${splash}/splash-ttf.c" $(pkg-config --libs freetype2) 2>&1); then
    out=$(A12_SPLASH_FONT="${font}" "${work}/splash-ttf-test" ttf 2>&1 &&
      A12_SPLASH_FONT=/nonexistent.ttf "${work}/splash-ttf-test" fallback 2>&1)
    report splash-ttf-test $? "${out}"
  else
    report splash-ttf-test 1 "${out}"
  fi
else
  echo "SKIP splash-ttf-test (FreeType headers or Liberation Sans not installed)"
  skipped=$((skipped + 1))
fi

if [ -r /usr/include/libdrm/drm.h ]; then
  if out=$(cc -std=c11 -O1 -Wall -Wextra -Werror -I/usr/include/libdrm \
      "${tests}/scanout-probe-fixture.c" -ldrm \
      -Wl,--wrap=drmModeAtomicAlloc -Wl,--wrap=drmModeAtomicAddProperty \
      -Wl,--wrap=drmModeAtomicCommit -Wl,--wrap=drmModeAtomicFree \
      -o "${work}/scanout-probe-fixture" 2>&1); then
    out=$("${work}/scanout-probe-fixture" 2>&1)
    report scanout-probe-fixture $? "${out}"
  else
    report scanout-probe-fixture 1 "${out}"
  fi
else
  echo "SKIP scanout-probe-fixture (libdrm headers not installed)"
  skipped=$((skipped + 1))
fi

echo "${failed} failed, ${skipped} skipped"
exit "${failed}"
