# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2024-present ROCKNIX (https://github.com/ROCKNIX)

. ${ROOT}/packages/audio/fluidsynth/package.mk

PKG_CMAKE_OPTS_TARGET="-DBUILD_SHARED_LIBS=1 \
                       -DLIB_SUFFIX= \
                       -Denable-libsndfile=1 \
                       -Denable-pkgconfig=1 \
                       -Denable-systemd=1 \
                       -Denable-readline=0"

if [ "${PIPEWIRE_SUPPORT}" = "yes" ]; then
  PKG_CMAKE_OPTS_TARGET+=" -Denable-pipewire=1 -Denable-pulseaudio=1"
else
  PKG_CMAKE_OPTS_TARGET+=" -Denable-pipewire=0 -Denable-pulseaudio=0"
fi

# A12: single-precision samples, and NEON for the per-voice float loops.
if [ "${DEVICE}" = "RK3128" ]; then
  PKG_CMAKE_OPTS_TARGET+=" -Denable-floats=1"
  pre_configure_target() {
    export CFLAGS+=" -funsafe-math-optimizations"
    export CXXFLAGS+=" -funsafe-math-optimizations"
  }
fi
