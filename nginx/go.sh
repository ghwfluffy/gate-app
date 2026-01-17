#!/bin/bash

set -eux -o pipefail

docker compose down -v -t0
docker compose build
docker compose up
