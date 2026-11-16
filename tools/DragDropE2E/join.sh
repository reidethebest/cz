#!/bin/bash
# Joins the local server through the menus (--join-server connects before Minecadia finishes loading and the client
# throws an NPE). Main menu: the 2nd button row (Multiplayer); then the DragDropE2E entry of servers.dat.
set -u
H=$(dirname "$0"); OUT=${OUT:-shots}; mkdir -p "$OUT"
for i in $(seq 1 90); do grep -aq "Finished loading Minecadia" client.out && break; sleep 2; done
sleep 8
W=$(xdotool search --name "Minecraft" 2>/dev/null | head -1)
xdotool getwindowgeometry $W
eval $(xdotool getwindowgeometry --shell $W)   # WIDTH HEIGHT X Y
S=1; while [ $((WIDTH / (S + 1))) -ge 320 ] && [ $((HEIGHT / (S + 1))) -ge 240 ]; do S=$((S + 1)); done
GW=$(( (WIDTH + S - 1) / S )); GH=$(( (HEIGHT + S - 1) / S ))
echo "gui scale $S, gui $GW x $GH"
at() { xdotool mousemove --window $W $(( $1 * S )) $(( $2 * S )); }
ready() { grep -q "DD READY" server/server.log; }
for try in 1 2 3; do
  ready && exit 0
  import -window root "$OUT/menu-$try.png"; python3 "$H/ocr.py" "$OUT/menu-$try.png"
  # vanilla GuiMainMenu: Multiplayer = button at y = height/4 + 48 + 24, 20 high, centered
  at $((GW / 2)) $((GH / 4 + 48 + 24 + 10)); xdotool click 1; sleep 3
  import -window root "$OUT/list-$try.png"; python3 "$H/ocr.py" "$OUT/list-$try.png"
  if p=$(python3 "$H/ocr.py" "$OUT/list-$try.png" dragdrop); then
    echo "entry by OCR at $p"; xdotool mousemove $p click --repeat 2 --delay 100 1
  else
    # vanilla GuiMultiplayer: list top = 32, first entry 36 high
    at $((GW / 2)) $((32 + 18)); xdotool click --repeat 2 --delay 100 1
  fi
  for s in $(seq 1 20); do ready && exit 0; sleep 1; done
  import -window root "$OUT/after-$try.png"; python3 "$H/ocr.py" "$OUT/after-$try.png"
  xdotool key Escape; sleep 1; xdotool key Escape; sleep 2
done
ready
