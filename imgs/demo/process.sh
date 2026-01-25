#!/usr/bin/env bash

set -euo pipefail

DELAY=150
convert -delay "${DELAY}" -loop 0 -resize 280x ./app-*.jpg ./app-03.jpg app.gif
