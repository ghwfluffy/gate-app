#!/bin/bash

SECRETS_DIR="$(dirname "${0}")/../secrets"
REFRESH_TOKEN="$(cat "${SECRETS_DIR}/refresh-token.txt")"
WEB_API_KEY="$(cat "${SECRETS_DIR}/web-api-key.txt")"

set -x
curl "https://securetoken.googleapis.com/v1/token?key=${WEB_API_KEY}" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data "grant_type=refresh_token&refresh_token=${REFRESH_TOKEN}"
