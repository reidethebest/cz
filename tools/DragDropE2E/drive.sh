#!/bin/bash
# Drives the real client with xdotool. Window 854x480 -> GUI scale 2, survival inventory at guiLeft=125 guiTop=37:
# slot (sx,sy) of GuiInventory has its center at window pixel ((133+sx)*2, (45+sy)*2).
set -u
OUT=${OUT:-out}; mkdir -p "$OUT"
W=$(xdotool search --name "Minecraft" 2>/dev/null | head -1)
[ -n "$W" ] || { echo "no Minecraft window"; exit 1; }
xdotool getwindowgeometry $W
mv_() { xdotool mousemove --window $W "$1" "$2"; }
px() { echo $(( (133 + 8 + 18 * $1) * 2 )); }      # column 0..8 -> x
ROW1=258; ROW2=294; HELMET_X=282; HELMET_Y=106
key() { xdotool keydown "$1"; sleep 0.12; xdotool keyup "$1"; sleep 0.4; }
chat() { key t; sleep 0.5; xdotool type --delay 40 "$1"; sleep 0.3; key Return; sleep 0.8; }
shot() { import -window root "$OUT/$1.png" 2>/dev/null || true; }
inv() { mv_ 427 240; key e; sleep 1.2; }
close() { key Escape; sleep 0.8; }

mv_ 427 240; sleep 1
chat ";t DragDrop"
shot 00-enabled

# Pass A (defaults: Stack, Delay 0): Q pressed while already on column 0 (vanilla drop must NOT fire too),
# one single jump to column 8 (the slots in between must still be thrown), slow way back (no re-throw),
# then up to the helmet (armor is skipped).
chat "/ddmark A"
inv; shot 01-inv
mv_ $(px 0) $ROW1; sleep 0.4
xdotool keydown q; sleep 0.4
mv_ $(px 8) $ROW1; sleep 0.4
for c in 7 6 5 4 3 2 1 0; do mv_ $(px $c) $ROW1; sleep 0.08; done
mv_ $HELMET_X $HELMET_Y; sleep 0.5
xdotool keyup q; sleep 1.5
shot 02-after-A
close

# Pass B: one item at a time with 150 ms between throws, cursor faster than the delay.
chat ";DragDrop Amount One"
chat ";DragDrop Delay 150"
chat "/ddmark B"
inv
mv_ $(px 0) $ROW2; sleep 0.3
xdotool keydown q; sleep 0.1
for c in 1 2 3 4 5 6 7 8 7 6 5 4 3 2 1 0; do mv_ $(px $c) $ROW2; sleep 0.04; done
sleep 2.5
xdotool keyup q; sleep 1
shot 03-after-B
close

# Pass C: RedropOnReenter, no delay: 0 -> 1 -> 0 -> 1 -> 0 throws column 0 three times and column 1 twice.
chat ";DragDrop Delay 0"
chat ";DragDrop RedropOnReenter true"
chat "/ddmark C"
inv
mv_ $(px 0) $ROW2; sleep 0.3
xdotool keydown q; sleep 0.3
for c in 1 0 1 0; do mv_ $(px $c) $ROW2; sleep 0.3; done
xdotool keyup q; sleep 1
close

# Pass D: module off: Q behaves like vanilla again (one item from the hovered slot only, no sweep).
chat ";t DragDrop"
chat "/ddfill"; sleep 1
chat "/ddmark D"
inv
mv_ $(px 2) $ROW1; sleep 0.3
xdotool keydown q; sleep 0.3
mv_ $(px 5) $ROW1; sleep 0.4
xdotool keyup q; sleep 1
close
chat "/ddmark END"
sleep 1
