#!/usr/bin/env bash

set -euo pipefail

IN="a681805f-3c56-4ad8-80d7-cc52718076b0.png"
TITLE="dog"
OUTDIR="${TITLE}-frames"
FPS="3"

mkdir -p "$OUTDIR"

# Split into tiles, write numbered PNGs
convert "$IN" -crop 4x6@ +repage +adjoin "$OUTDIR/frame_%02d.png"

# Build an animated GIF from the tiles (in filename order), loop forever
DELAY=$(( 100 / FPS ))  # ImageMagick delay is in 1/100s
convert -delay "$DELAY" -loop 0 "$OUTDIR"/frame_*.png "${TITLE}.gif"
