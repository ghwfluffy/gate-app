#!/usr/bin/env bash

set -euo pipefail

IN="b215e85e-8c80-4f0a-a54f-5a5a47838ec7.png"
OUTDIR="frames"
FPS="3"

mkdir -p "$OUTDIR"

# Split into 36 tiles (6x6), write numbered PNGs
convert "$IN" -crop 4x8@ +repage +adjoin "$OUTDIR/frame_%02d.png"

# Build an animated GIF from the tiles (in filename order), loop forever
DELAY=$(( 100 / FPS ))  # ImageMagick delay is in 1/100s
convert -delay "$DELAY" -loop 0 "$OUTDIR"/frame_*.png cats.gif
