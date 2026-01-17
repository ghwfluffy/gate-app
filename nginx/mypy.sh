#!/bin/bash

set -eu -o pipefail

if [ ! -d venv ]; then
    python3 -m venv venv
fi

source ./venv/bin/activate
python3 -m pip install mypy flask requests types-requests &> /dev/null

mypy --check-untyped-defs ./proxy.py
