#!/bin/bash
# SPDX-License-Identifier: GPL-2.0
# Copyright (C) 2023 JELOS (https://github.com/JustEnoughLinuxOS)

###
### Normally this would be a udev rule, but some devices like the AyaNeo Air
### do not properly report the applied power state to udev, and we can't use
### inotifyd to watch the status in /sys.
###

. /etc/profile

BATCNT=0
unset CURRENT_MODE
unset AC_STATUS
ledcontrol $(get_setting led.color)

### Poll without starting processes: every new one keeps schedutil up.
WAIT=/tmp/.powerstate.wait
rm -f "${WAIT}"
mkfifo "${WAIT}"
exec 3<>"${WAIT}"
rm -f "${WAIT}"

while true; do
  ### The battery driver may register after this service starts.
  [ -d "${BATDIR}" ] || for BATDIR in /sys/class/power_supply/[bB][aA][tT]*; do break; done
  AC_STATUS=""
  read -r AC_STATUS 2>/dev/null <"${BATDIR}/status"
  if [[ ! "${CURRENT_MODE}" =~ ${AC_STATUS} ]]; then
    case ${AC_STATUS} in
      Disch*)
        log $0 "Switching to battery mode."
        if [ -e "/tmp/.gpu_performance_level" ]; then
          GPUPROFILE=$(cat /tmp/.gpu_performance_level)
        else
          GPUPROFILE=$(get_setting system.gpuperf)
        fi
        if [ -z "${GPUPROFILE}" ]; then
          GPUPROFILE="auto"
        fi
        gpu_performance_level ${GPUPROFILE}
        if [ "${DEVICE_LED_CHARGING}" = "true" ]; then
          ledcontrol discharging
        fi
      ;;
      *)
        log $0 "Switching to performance mode."
        GPUPROFILE=$(cat /tmp/.gpu_performance_level 2>/dev/null || :)
        gpu_performance_level "${GPUPROFILE:-auto}"
        if [ "${DEVICE_LED_CHARGING}" = "true" ]; then
          ledcontrol charging
        fi
      ;;
    esac
    CURRENT_MODE="${AC_STATUS}"
  fi
  ### Until we have an overlay. :rofl:
  BATLEFT=""
  if [ -f /tmp/battery.percent ]; then
    read -r BATLEFT </tmp/battery.percent
  else
    read -r BATLEFT 2>/dev/null <"${BATDIR}/capacity"
  fi
  if ! [[ "${BATLEFT}" =~ ^[0-9]+$ ]]; then
    read -r -t 2 -u 3 _
    continue
  fi
  if (( "${BATCNT}" >= "20" )) && [[ "${AC_STATUS}" =~ Disch ]]; then
    AUDIBLEALERT=$(get_setting system.battery.warning)
    AUDIBLEALERT_THRESHOLD=$(get_setting system.battery.warning_threshold)
    [[ -z $AUDIBLEALERT_THRESHOLD ]] && AUDIBLEALERT_THRESHOLD=25

    if [[ ${BATLEFT} -le ${AUDIBLEALERT_THRESHOLD} ]]; then
      if [ "${DEVICE_LED_CONTROL}" = "true" ] && [ ! "${DEVICE_BATTERY_LED_STATUS}" = "true" ]; then
        # Flash the RGB or power LED if available.
        led_flash
        BATCNT=0
      elif [ "${AUDIBLEALERT}" = "1" ]; then
        say "BATTERY AT ${BATLEFT}%"
        BATCNT=0
      fi
    fi
  elif (( "${BATLEFT}" > "97" )); then
    if [ "${DEVICE_LED_CHARGING}" = "true" ]; then
      # Reset the LED as if the battery was full.
      ledcontrol discharging
    fi
  fi
  BATCNT=$(( ${BATCNT} + 1 ))
  read -r -t 2 -u 3 _
done
