#!/bin/bash

REFRESH_TOKEN="<Token Here>"
WEB_API_KEY="<API Key Here>"

set -x
curl "https://securetoken.googleapis.com/v1/token?key=${WEB_API_KEY}" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data "grant_type=refresh_token&refresh_token=${REFRESH_TOKEN}"
