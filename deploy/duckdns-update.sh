#!/usr/bin/env bash
set -euo pipefail

: "${DUCKDNS_SUBDOMAIN:?DUCKDNS_SUBDOMAIN not set}"
: "${DUCKDNS_TOKEN:?DUCKDNS_TOKEN not set}"

response="$(curl -fsS "https://www.duckdns.org/update?domains=${DUCKDNS_SUBDOMAIN}&token=${DUCKDNS_TOKEN}&ip=")"

if [[ "$response" != "OK" ]]; then
    echo "nomiflix: duckdns update failed: $response" >&2
    exit 1
fi

echo "nomiflix: duckdns updated ($DUCKDNS_SUBDOMAIN)"
