# SPDX-License-Identifier: GPL-2.0
PKG_NAME="a12-free-games"
PKG_VERSION="1.9.fixed-4"
PKG_SHA256="29c673d3ed41fb9ab64b3f3907ab9d17e2ca861b1cd6f4aca53aced79d257d0e"
PKG_LICENSE="freely distributable"
PKG_SITE="https://packages.debian.org/doom-wad-shareware"
# Doom 1.9 shareware, freely distributable (id Software; see the copyright
# file). Taken from Debian at build time: no game data in the repository.
PKG_URL="https://deb.debian.org/debian/pool/non-free/d/doom-wad-shareware/doom-wad-shareware_${PKG_VERSION}_all.deb"
PKG_DEPENDS_TARGET="toolchain"
PKG_LONGDESC="Freely distributable games for a fresh A12 card"
PKG_TOOLCHAIN="manual"

# Further games, "name url sha256", fetched into the sources cache at build
# time. Freedoom: BSD. Tobu Tobu Girl (DX): MIT code, CC BY 4.0 assets, ROMs
# from the gbdev Homebrew Hub. The rest is the homebrew Batocera ships,
# without a licence file: credits next to each, removed on request.
A12_FREE_GAMES_FILES="
freedoom-0.13.0.zip https://github.com/freedoom/freedoom/releases/download/v0.13.0/freedoom-0.13.0.zip 3f9b264f3e3ce503b4fb7f6bdcb1f419d93c7b546f4df3e874dd878db9688f59
tobu.gb https://raw.githubusercontent.com/gbdev/database/94368e51470f14fe5c495e6e65c994f2c3b6c661/entries/tobutobugirl/tobu.gb 5d3871cae77db2287807e8914fd21f76203e73aa3fec20955489d45cb4571d8f
tobudx.gb https://raw.githubusercontent.com/gbdev/database/94368e51470f14fe5c495e6e65c994f2c3b6c661/entries/tobutobugirldeluxe/tobudx.gb 0a0e8018dbbc8d7f8cd99f05e7cdc7b4cc9e358ecfe9377ebfb2291a84c6e310
Old-Towers.bin https://raw.githubusercontent.com/batocera-linux/batocera.linux/5f6d4f30fa6245c7f4a38bd18f3fd876e42be720/package/batocera/emulationstation/batocera-es-system/roms/megadrive/Old-Towers.bin 39cd650d9225785e9c93d3beb8ba95334eb16077ab930cbfe5f75d9999991576
SpaceTwins.gba https://raw.githubusercontent.com/batocera-linux/batocera.linux/5f6d4f30fa6245c7f4a38bd18f3fd876e42be720/package/batocera/emulationstation/batocera-es-system/roms/gba/SpaceTwins.gba ff868c2cef798376cf7e2fa4a5f27ff6b7ec2e00ef50331877306c3326abc13c
Reflectron.pce https://raw.githubusercontent.com/batocera-linux/batocera.linux/5f6d4f30fa6245c7f4a38bd18f3fd876e42be720/package/batocera/emulationstation/batocera-es-system/roms/pcengine/Reflectron%20(aetherbyte).pce ca418662637bacab78fa05dea0f346a876994ecc58b636d4121a4409c2979e48
Santatlantean.pce https://raw.githubusercontent.com/batocera-linux/batocera.linux/5f6d4f30fa6245c7f4a38bd18f3fd876e42be720/package/batocera/emulationstation/batocera-es-system/roms/pcengine/Santatlantean%20(aetherbyte).pce d5efc0bee6a78e61faa13f9d97d700cb8a377ca150b3bfa5ff0cd2ccdf2262d5
"

a12_fetch() {
  local file="${SOURCES}/${PKG_NAME}/${1}"
  if ! echo "${3}  ${file}" | sha256sum -c --status 2>/dev/null; then
    curl -fsSL --retry 3 -o "${file}.part" "${2}" && mv "${file}.part" "${file}"
  fi
  echo "${3}  ${file}" | sha256sum -c --status || die "a12-free-games: ${1} does not match its sha256"
}

unpack() {
  mkdir -p ${PKG_BUILD}
  cd ${PKG_BUILD}
  ar x ${SOURCES}/${PKG_NAME}/${PKG_NAME}-${PKG_VERSION}.deb
  tar -xf data.tar.xz
  # Not a pipe: die must stop the build, not a subshell.
  while read -r name url sha; do
    [ -n "${name}" ] && a12_fetch "${name}" "${url}" "${sha}"
  done <<< "${A12_FREE_GAMES_FILES}"
  unzip -qo ${SOURCES}/${PKG_NAME}/freedoom-0.13.0.zip
}

makeinstall_target() {
  local share=${INSTALL}/usr/share/a12-free-games src=${SOURCES}/${PKG_NAME} fd=${PKG_BUILD}/freedoom-0.13.0
  mkdir -p ${share}/doom ${share}/gb ${share}/megadrive ${share}/gba ${share}/pcengine
  cp ${PKG_BUILD}/usr/share/games/doom/doom1.wad ${share}/doom/
  cp ${PKG_BUILD}/usr/share/doc/doom-wad-shareware/copyright ${share}/doom/doom1.wad.copyright.txt
  cp ${fd}/freedoom1.wad ${fd}/freedoom2.wad ${share}/doom/
  cp ${fd}/COPYING.txt ${share}/doom/freedoom.COPYING.txt
  cp ${fd}/CREDITS.txt ${share}/doom/freedoom.CREDITS.txt
  cp ${src}/tobu.gb "${share}/gb/Tobu Tobu Girl.gb"
  cp ${src}/tobudx.gb "${share}/gb/Tobu Tobu Girl Deluxe.gb"
  cp ${PKG_DIR}/sources/credits/tobu.licence.txt "${share}/gb/Tobu Tobu Girl.licence.txt"
  cp ${src}/Old-Towers.bin "${share}/megadrive/Old Towers.bin"
  cp ${PKG_DIR}/sources/credits/old-towers.credits.txt "${share}/megadrive/Old Towers.credits.txt"
  cp ${src}/SpaceTwins.gba "${share}/gba/Space Twins.gba"
  cp ${PKG_DIR}/sources/credits/space-twins.credits.txt "${share}/gba/Space Twins.credits.txt"
  cp ${src}/Reflectron.pce ${src}/Santatlantean.pce ${share}/pcengine/
  cp ${PKG_DIR}/sources/credits/aetherbyte.credits.txt ${share}/pcengine/Aetherbyte.credits.txt
  # Writes to /storage/roms: device stage, after automount.
  mkdir -p ${INSTALL}/usr/lib/autostart/RK3128
  cp ${PKG_DIR}/sources/023-a12-free-games ${INSTALL}/usr/lib/autostart/RK3128/
  chmod 0755 ${INSTALL}/usr/lib/autostart/RK3128/023-a12-free-games
}
