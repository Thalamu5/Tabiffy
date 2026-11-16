#!/bin/sh
# Starts as root only to make sure the app's user owns the data folder (older versions created it as
# root, which made every upload fail), then runs the app as that unprivileged user.
set -e
if [ "$(id -u)" = "0" ]; then
  if [ -n "$(find /data ! -user tabiffy -print -quit 2>/dev/null)" ]; then
    chown -R tabiffy:tabiffy /data
  fi
  export HOME=/home/tabiffy  # setpriv keeps root's HOME, which the app user can't write to
  exec setpriv --reuid=tabiffy --regid=tabiffy --init-groups "$@"
fi
exec "$@"
