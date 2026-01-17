#!/bin/bash

GET_TOKEN="$(dirname "${0}")/get-token.sh"
TOKEN="$("${GET_TOKEN}" 2>&1 | grep access_token | cut -d'"' -f4)"

set -x
curl https://api-v2.gatewise.com/api/v1/user/community/2524/access_point/8211/open? \
    -H "Accept: application/json" \
    -H "Cache-Control: no-cache" \
    -H "Authorization: Bearer ${TOKEN}" \
    --data '{}'
