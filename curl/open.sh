#!/bin/bash

set -x

TOKEN="<Redacted>"
DEVICE_UUID="<uuid>

curl https://api-v2.gatewise.com/api/v1/user/community/2524/access_point/8211/open? \
    -H "Accept: application/json" \
    -H "Cache-Control: no-cache" \
    -H "Authorization: Bearer ${TOKEN}" \
    --data '{}'

    #-H "Device-Token: ${DEVICE_UUID}" \
