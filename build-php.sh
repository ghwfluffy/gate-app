#!/bin/bash

set -eu -o pipefail

TOPDIR="$(dirname "${0}")"

WWW="${TOPDIR}/www"
FINAL="${WWW}/index.php"

REFRESH_TOKEN_FILE="${TOPDIR}/secrets/refresh-token.txt"
WEB_API_KEY_FILE="${TOPDIR}/secrets/web-api-key.txt"
PHP_PW_FILE="${TOPDIR}/secrets/php-pw.txt"
if [ ! -f "${REFRESH_TOKEN_FILE}" ]; then
    echo "No refresh token found." 1>&2
    echo "You must first login to the Gatewise app and steal the Firebrase refresh token from the filesystem." 1>&2
    exit 1
fi
if [ ! -f "${WEB_API_KEY_FILE}" ]; then
    echo "No web API key found." 1>&2
    echo "You can discover this inside of the Gatewise app source code." 1>&2
    exit 2
fi

REFRESH_TOKEN="$(cat "${REFRESH_TOKEN_FILE}")"
WEB_API_KEY="$(cat "${WEB_API_KEY_FILE}")"
if [ -f "${PHP_PW_FILE}" ]; then
    PASSWORD="$(cat "${PHP_PW_FILE}")"
else
    PASSWORD="$(dd if=/dev/urandom bs=1 count=16 2> /dev/null | base64 | sed 's;[+/=]*;;g')"
    echo "${PASSWORD}" > "${PHP_PW_FILE}"
fi

PHP_HEADER="$(cat << PHP
<?php

session_start();

// Check auth
if (!empty(\$_GET['pw']))
{
    if (!empty(\$_GET['pw']) && \$_GET['pw'] == "${PASSWORD}")
    {
        \$_SESSION['GateAccess'] = true;
    }
}

if (empty(\$_SESSION['GateAccess']))
{
    die('
<html>
<body>
    <center>
        <font color=red>Access Denied</font>
    </center>
</body>
</html>
');
}
?>
PHP
)"

# This lets chrome turn the web page into an app
APP_MANIFEST="$(cat << MAN
{
  "name": "Ghw Gate",
  "short_name": "Ghw Gate",
  "description": "Ghw Gate",
  "start_url": "/gate/index.php?pw=${PASSWORD}",
  "scope": "/gate/",
  "display": "standalone",
  "background_color": "#0b0f14",
  "theme_color": "#0b0f14",
  "orientation": "any",
  "icons": [
    {
      "src": "/gate/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/gate/icons/icon-192-maskable.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "maskable"
    },
    {
      "src": "/gate/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/gate/icons/icon-512-maskable.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "maskable"
    }
  ],
  "categories": ["utilities", "productivity"],
  "lang": "en",
  "dir": "ltr"
}
MAN
)"

echo "${PHP_HEADER}" > "${FINAL}"
cat "${WWW}/index.html" | sed "s;%REFRESH_TOKEN%;${REFRESH_TOKEN};g" | sed "s;%WEB_API_KEY%;${WEB_API_KEY};g" >> "${FINAL}"

echo "${APP_MANIFEST}" > "${WWW}/manifest.json"

echo "Generated index PHP with password ${PASSWORD}"
