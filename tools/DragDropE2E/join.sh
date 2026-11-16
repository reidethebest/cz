#!/bin/bash
# Joins the local server through the menus (the --join-server flag connects before Minecadia finishes loading and
# the client throws an NPE). Buttons are found by OCR, so a custom main menu does not break it.
set -u
H=$(dirname "$0"); OUT=${OUT:-shots}; mkdir -p "$OUT"
for i in $(seq 1 90); do grep -aq "Finished loading Minecadia" client.out && break; sleep 2; done
sleep 8
for try in 1 2 3 4; do
  grep -q "DD READY" server/server.log && exit 0
  import -window root "$OUT/menu-$try.png"; python3 "$H/ocr.py" "$OUT/menu-$try.png"
  if p=$(python3 "$H/ocr.py" "$OUT/menu-$try.png" DragDropE2E); then
    xdotool mousemove $p click --repeat 2 --delay 120 1
  elif p=$(python3 "$H/ocr.py" "$OUT/menu-$try.png" multiplayer); then
    xdotool mousemove $p click 1
  elif p=$(python3 "$H/ocr.py" "$OUT/menu-$try.png" back); then
    xdotool mousemove $p click 1
  else
    xdotool key Escape
  fi
  for s in $(seq 1 15); do grep -q "DD READY" server/server.log && exit 0; sleep 1; done
done
grep -q "DD READY" server/server.log
