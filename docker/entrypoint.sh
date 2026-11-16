#!/bin/sh
# Runs the app as PUID:PGID (Unraid default 99:100, nobody:users) and makes sure /config is writable.
set -e

DATA="${PRINTMICH_DATA:-/config}"
mkdir -p "$DATA"

if [ "$(id -u)" = "0" ]; then
  PUID="${PUID:-99}"
  PGID="${PGID:-100}"
  if [ "$(stat -c '%u:%g' "$DATA")" != "$PUID:$PGID" ]; then
    echo "Printmich: setting owner of $DATA to $PUID:$PGID"
    chown -R "$PUID:$PGID" "$DATA" || echo "Printmich: could not change owner of $DATA, continuing"
  fi
  umask "${UMASK:-002}"
  exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups -- "$@"
fi

exec "$@"
