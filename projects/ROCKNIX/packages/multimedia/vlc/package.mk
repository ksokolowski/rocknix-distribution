# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2019-present Shanti Gilbert (https://github.com/shantigilbert)
# Copyright (C) 2023 JELOS (https://github.com/JustEnoughLinuxOS)

PKG_NAME="vlc"
PKG_VERSION="3.0.23"
PKG_SHA256="e891cae6aa3ccda69bf94173d5105cbc55c7a7d9b1d21b9b21666e69eff3e7e0"
PKG_LICENSE="GPL"
PKG_SITE="http://www.videolan.org"
PKG_URL="https://mirror.netcologne.de/videolan.org/${PKG_NAME}/${PKG_VERSION}/$PKG_NAME-${PKG_VERSION}.tar.xz"
PKG_DEPENDS_TARGET="toolchain libdvbpsi gnutls ffmpeg libmpeg2 zlib flac libvorbis libxml2 pulseaudio SDL2 x264 x265 aom libogg"
PKG_LONGDESC="VideoLAN multimedia player and streamer"
PKG_TOOLCHAIN="autotools"

# On the A12 VLC only plays ES's preview videos (libVLC vmem, RGBA) and
# grabs ES's thumbnails (PNG snapshot, scene filter with JPEG, dummy vout):
# FFmpeg decodes, ALSA plays (no PulseAudio server), no network, streaming
# or GL output. RAM is 256 MiB, so build and keep only that
# (plans/2026-10-12-a12-vlc-brief.md). --enable-sout stays: the image
# encoders behind snapshots and the scene filter are in the core's sout code.
if [ "${DEVICE}" = "RK3128" ]; then
  PKG_DEPENDS_TARGET="toolchain ffmpeg zlib alsa-lib libpng libjpeg-turbo"
  # Rebuild when FFmpeg changes: its sonames move with major versions, and
  # a stale VLC links libraries the image no longer has (sync 2026-10-17).
  PKG_NEED_UNPACK+=" $(get_pkg_directory ffmpeg)"

  A12_VLC_FEATURES="--enable-silent-rules --enable-run-as-root --enable-optimize-memory \
            --disable-dependency-tracking --without-contrib --disable-nls --disable-rpath \
            --disable-debug --disable-static --enable-neon --enable-vlc \
            --enable-avcodec --enable-avformat --enable-swscale --enable-png --enable-jpeg \
            --enable-alsa --disable-pulse --disable-oss --disable-sndio --disable-jack \
            --disable-samplerate --disable-soxr --disable-speex \
            --enable-sout --disable-vlm --disable-lua --disable-addonmanagermodules \
            --disable-dbus --disable-udev --disable-v4l2 --disable-vcd --disable-libcddb \
            --disable-archive --disable-live555 --disable-dc1394 --disable-dv1394 \
            --disable-linsys --disable-dvdread --disable-dvdnav --disable-bluray \
            --disable-smbclient --disable-dsm --disable-sftp --disable-nfs --disable-smb2 \
            --disable-screen --disable-vnc --disable-freerdp --disable-realrtsp \
            --disable-decklink --disable-asdcp --disable-dvbpsi --disable-gme --disable-sid \
            --disable-ogg --disable-shout --disable-matroska --disable-mod --disable-mpc \
            --disable-shine --disable-omxil --disable-crystalhd --disable-mad --disable-mpg123 \
            --disable-gst-decode --disable-merge-ffmpeg --disable-libva --disable-postproc \
            --disable-faad --disable-aom --disable-dav1d --disable-vpx --disable-twolame \
            --disable-fdkaac --disable-a52 --disable-dca --disable-flac --disable-libmpeg2 \
            --disable-vorbis --disable-tremor --disable-opus --disable-spatialaudio \
            --disable-theora --disable-oggspots --disable-daala --disable-schroedinger \
            --disable-bpg --disable-x262 --disable-x265 --disable-x264 --disable-x26410b \
            --disable-mfx --disable-fluidsynth --disable-fluidlite --disable-zvbi \
            --disable-telx --disable-aribsub --disable-aribb25 --disable-kate --disable-tiger \
            --disable-css --disable-gles2 --without-x --disable-xcb --disable-xvideo \
            --disable-vdpau --disable-wayland --disable-sdl-image --disable-freetype \
            --disable-fribidi --disable-harfbuzz --disable-fontconfig --disable-libass \
            --disable-svg --disable-svgdec --disable-aa --disable-caca --disable-mmal \
            --disable-evas --disable-chromaprint --disable-chromecast --disable-qt \
            --disable-skins2 --disable-ncurses --disable-lirc --disable-srt --disable-goom \
            --disable-projectm --disable-vsxu --disable-avahi --disable-mtp --disable-upnp \
            --disable-microdns --disable-libxml2 --disable-libgcrypt --disable-gnutls \
            --disable-taglib --disable-secret --disable-kwallet --disable-update-check \
            --disable-notify --disable-libplacebo"

  # Plugins kept after install, relative to /usr/lib/vlc/plugins; VLC builds
  # most modules whatever configure says. libVLC needs none to start; a
  # local MP4 preview needs file access, the MP4 demuxer (others through
  # avformat), packetizers, avcodec, the chroma converters, vmem, ALSA or
  # the dummy output and the audio conversion chain. ES's thumbnails add
  # the scene filter, the JPEG/PNG encoders and the dummy vout; cvlc adds
  # the dummy interface and the console logger.
  A12_VLC_PLUGINS="access/libfilesystem_plugin.so access/libidummy_plugin.so
            arm_neon/libchroma_yuv_neon_plugin.so arm_neon/libvolume_neon_plugin.so
            arm_neon/libyuv_rgb_neon_plugin.so
            audio_filter/libaudio_format_plugin.so audio_filter/libremap_plugin.so
            audio_filter/libsimple_channel_mixer_plugin.so
            audio_filter/libtrivial_channel_mixer_plugin.so
            audio_filter/libscaletempo_plugin.so audio_filter/libugly_resampler_plugin.so
            audio_mixer/libfloat_mixer_plugin.so audio_mixer/libinteger_mixer_plugin.so
            audio_output/libadummy_plugin.so audio_output/libafile_plugin.so
            audio_output/libalsa_plugin.so audio_output/libamem_plugin.so
            codec/libavcodec_plugin.so codec/libaraw_plugin.so codec/libjpeg_plugin.so
            codec/libpng_plugin.so codec/librawvideo_plugin.so
            control/libdummy_plugin.so
            demux/libavformat_plugin.so demux/libes_plugin.so demux/libmp4_plugin.so
            logger/libconsole_logger_plugin.so
            packetizer/libpacketizer_copy_plugin.so packetizer/libpacketizer_h264_plugin.so
            packetizer/libpacketizer_hevc_plugin.so packetizer/libpacketizer_mpeg4audio_plugin.so
            packetizer/libpacketizer_mpeg4video_plugin.so
            packetizer/libpacketizer_mpegaudio_plugin.so
            stream_filter/libcache_read_plugin.so stream_filter/libprefetch_plugin.so
            stream_filter/libskiptags_plugin.so
            video_chroma/libchain_plugin.so video_chroma/libi420_rgb_plugin.so
            video_chroma/libi420_yuy2_plugin.so video_chroma/libi422_i420_plugin.so
            video_chroma/libswscale_plugin.so video_chroma/libyuvp_plugin.so
            video_chroma/libyuy2_i420_plugin.so
            video_filter/libdeinterlace_plugin.so video_filter/libscene_plugin.so
            video_filter/libtransform_plugin.so
            video_output/libvdummy_plugin.so video_output/libvmem_plugin.so"
fi

pre_configure_target() {
  export CFLAGS="${CFLAGS} -Wno-error=incompatible-pointer-types"
  export CXXLFAGS="${CXXFLAGS} -Wno-error=incompatible-pointer-types"
  export BUILDCC="${TOOLCHAIN}/bin/host-gcc"

  if [ "${DEVICE}" = "RK3128" ]; then
    PKG_CONFIGURE_OPTS_TARGET="${A12_VLC_FEATURES}"
    # glibc 2.41+ refuses to dlopen() a library that asks for an executable
    # stack: no VLC plugin may (patch 0002 fixes VLC's own assembly).
    export LDFLAGS="${LDFLAGS} -Wl,-z,noexecstack -lresolv -Wl,-rpath,../src/.libs"
    return
  fi

  ENABLED_FEATURES="--enable-silent-rules \
            --enable-run-as-root \
            --enable-sout \
            --enable-vlm \
            --enable-v4l2 \
            --enable-mpc \
            --enable-avcodec \
            --enable-avformat \
            --enable-swscale \
            --enable-postproc \
            --enable-aa \
            --enable-libmpeg2 \
            --enable-png \
            --enable-jpeg \
            --enable-libxml2 \
            --enable-pulse \
            --enable-udev \
            --enable-vlc \
            --enable-x264"

  DISABLED_FEATURES="--disable-dependency-tracking \
            --without-contrib \
            --disable-alsa \
            --disable-nls \
            --disable-dbus \
            --disable-gprof \
            --disable-cprof \
            --disable-rpath \
            --disable-debug \
            --disable-coverage \
            --disable-lua \
            --disable-notify \
            --disable-taglib \
            --disable-live555 \
            --disable-dc1394 \
            --disable-dvdread \
            --disable-dvdnav \
            --disable-opencv \
            --disable-decklink \
            --disable-sftp \
            --disable-vcd \
            --disable-libcddb \
            --disable-dvbpsi \
            --disable-screen \
            --disable-ogg \
            --disable-shout\
            --disable-mod \
            --disable-gme \
            --disable-wma-fixed \
            --disable-shine \
            --disable-omxil \
            --disable-mad \
            --disable-merge-ffmpeg \
            --disable-faad \
            --disable-flac \
            --disable-twolame \
            --disable-realrtsp \
            --disable-libtar \
            --disable-a52 \
            --disable-dca \
            --disable-vorbis \
            --disable-tremor \
            --disable-speex \
            --disable-theora \
            --disable-schroedinger \
            --disable-fluidsynth \
            --disable-zvbi \
            --disable-telx \
            --disable-libass \
            --disable-kate \
            --disable-tiger \
            --disable-libva \
            --disable-vdpau \
            --without-x \
            --disable-xcb \
            --disable-xvideo \
            --disable-sdl-image \
            --disable-freetype \
            --disable-fribidi \
            --disable-fontconfig \
            --disable-svg \
            --disable-directx \
            --disable-caca \
            --disable-oss \
            --disable-jack \
            --disable-upnp \
            --disable-skins2 \
            --disable-kai \
            --disable-macosx \
            --disable-ncurses \
            --disable-goom \
            --disable-projectm \
            --disable-mtp \
            --disable-lirc \
            --disable-libgcrypt \
            --disable-update-check \
            --disable-kva \
            --disable-bluray \
            --disable-samplerate \
            --disable-sid \
            --disable-crystalhd \
            --disable-dxva2 \
            --disable-dav1d \
            --disable-qt \
            --disable-x26410b \
            --disable-chromecast \
            --disable-static \
            --disable-a52 \
            --disable-addonmanagermodules \
            --disable-aom \
            --disable-aribb25 \
            --disable-aribsub \
            --disable-asdcp \
            --disable-bpg \
            --disable-caca \
            --disable-chromaprint \
            --disable-chromecast \
            --disable-crystalhd \
            --disable-dc1394 \
            --disable-dca \
            --disable-decklink \
            --disable-dsm \
            --disable-dv1394 \
            --disable-fluidlite \
            --disable-gme \
            --disable-goom \
            --disable-jack \
            --disable-kai \
            --disable-kate \
            --disable-kva \
            --disable-libplacebo \
            --disable-linsys \
            --disable-mfx \
            --disable-microdns \
            --disable-mmal \
            --disable-mtp \
            --disable-notify \
            --disable-projectm \
            --disable-shine \
            --disable-shout \
            --disable-sndio \
            --disable-spatialaudio \
            --disable-srt \
            --disable-telx \
            --disable-tiger \
            --disable-twolame \
            --disable-vdpau \
            --disable-vsxu \
            --disable-wasapi \
            --disable-x262 \
            --disable-zvbi"

  case ${ARCH} in
    arm)
      PKG_DEPENDS_TARGET+=" ${OPENGLES}"
      ENABLED_FEATURES+=" --enable-gles2 --enable-neon"
    ;;
    aarch64)
      PKG_DEPENDS_TARGET+=" ${OPENGLES}"
      ENABLED_FEATURES+=" --enable-gles2"
    ;;
    *)
      PKG_DEPENDS_TARGET+=" ${OPENGL} glu libglvnd"
    ;;
  esac

  PKG_CONFIGURE_OPTS_TARGET="${DISABLED_FEATURES} ${ENABLED_FEATURES}"
  export LDFLAGS="${LDFLAGS} -lresolv -fopenmp -Wl,-rpath,../src/.libs"
}

post_makeinstall_target() {
  rm -fr ${INSTALL}/usr/share/applications
  rm -fr ${INSTALL}/usr/share/icons
  rm -fr ${INSTALL}/usr/share/kde4
  rm -f ${INSTALL}/usr/bin/rvlc
  rm -f ${INSTALL}/usr/bin/vlc-wrapper

  if [ "${DEVICE}" = "RK3128" ]; then
    local plugins="${INSTALL}/usr/lib/vlc/plugins" plugin
    for plugin in $(cd "${plugins}" && find . -name '*.so' | sed 's|^\./||'); do
      case " $(echo ${A12_VLC_PLUGINS}) " in
        *" ${plugin} "*) ;;
        *) rm -f "${plugins}/${plugin}" ;;
      esac
    done
    find "${plugins}" -type d -empty -delete
    # /usr is read-only: a12-vlc-cache (a12-controls) builds the cache there.
    ln -sf /storage/.cache/vlc/plugins/plugins.dat "${plugins}/plugins.dat"
    rm -fr ${INSTALL}/usr/share/vlc ${INSTALL}/usr/share/doc ${INSTALL}/usr/share/man
  fi
}
