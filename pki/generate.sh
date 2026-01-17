#!/usr/bin/env bash

set -euo pipefail

PKIDIR="$(dirname "$(realpath "${0}")")"
CONF="${PKIDIR}/openssl.conf"
OUT="${PKIDIR}/data"

mkdir -p "${OUT}"
cd "${OUT}"

if [ -f ./server.crt ]; then
    echo "Already generated" 1>&2
    exit 1
fi

DAYS_ROOT=3650      # ~10y
DAYS_ISSUING=1825   # ~5y
DAYS_SERVER=365     # 1y

ROOT_NAME="Ghw Trust Services Root CA"
ISSUING_NAME="Ghw Secure Issuing CA 01"

# 1) Root key + self-signed root cert
openssl genrsa -out root.key 2048
openssl req -new -x509 -sha256 -days "${DAYS_ROOT}" \
  -key root.key \
  -subj "/C=US/O=Ghw Trust Services, Inc./CN=${ROOT_NAME}" \
  -out root.crt \
  -config "${CONF}" -extensions v3_root

# 2) Issuing CA key + CSR, signed by Root
openssl genrsa -out issuing-ca.key 2048
openssl req -new -sha256 \
  -key issuing-ca.key \
  -subj "/C=US/O=Ghw Trust Services, Inc./CN=${ISSUING_NAME}" \
  -out issuing-ca.csr

openssl x509 -req -sha256 -days "${DAYS_ISSUING}" \
  -in issuing-ca.csr \
  -CA root.crt -CAkey root.key -CAcreateserial \
  -out issuing-ca.crt \
  -extfile "${CONF}" -extensions v3_ca

# 3) Server key + CSR for server, signed by Issuing CA (includes SANs from openssl.conf)
openssl genrsa -out server.key 2048
openssl req -new -sha256 \
  -key server.key \
  -subj "/C=US/O=Ghw Web Services/CN=api-v2.gatewise.com" \
  -out server.csr

openssl x509 -req -sha256 -days "${DAYS_SERVER}" \
  -in server.csr \
  -CA issuing-ca.crt -CAkey issuing-ca.key -CAcreateserial \
  -out server.crt \
  -extfile "${CONF}" -extensions v3_tlserver

# Chain file (server + issuing; root typically distributed separately)
cat server.crt issuing-ca.crt > server-chain.crt

# Quick verification + display
openssl verify -CAfile root.crt -untrusted issuing-ca.crt server.crt
openssl x509 -in server.crt -noout -subject -issuer -ext subjectAltName
echo "Wrote: root.crt issuing-ca.crt server.crt server-chain.crt (keys in *.key)"
