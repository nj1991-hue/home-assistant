#!/bin/bash

# Usage: ./get_tado_rooms_devices.sh <home_id>

HOME_ID="$1"

if [ -z "$HOME_ID" ]; then
  echo "Usage: $0 <home_id>"
  exit 1
fi

# Temporary file to store the response
TEMP_FILE=$(mktemp)

# Make the request, capturing status code and storing body in TEMP_FILE
HTTP_STATUS=$(curl -s -w "%{http_code}" -o "$TEMP_FILE" \
  "https://hops.tado.com/homes/${HOME_ID}/roomsAndDevices?ngsw-bypass=true" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0" \
  -H "Accept: application/json, text/plain, */*" \
  -H "Accept-Language: it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3" \
  -H "Accept-Encoding: gzip, deflate, br, zstd" \
  -H "Referer: https://app.tado.com/" \
  -H "X-Amzn-Trace-Id: tado=webapp-2025.3.7.9.55-release/v3677" \
  -H "Origin: https://app.tado.com" \
  -H "Sec-Fetch-Dest: empty" \
  -H "Sec-Fetch-Mode: cors" \
  -H "Sec-Fetch-Site: same-site" \
  -H "Authorization: Bearer $(jq -r '.access_token' /config/tado_response.json)" \
  -H "Connection: keep-alive" \
  -H "TE: trailers")

# Check if the HTTP status code is 200
if [ "$HTTP_STATUS" -eq 200 ]; then
  mv "$TEMP_FILE" "/config/tado_rooms_devices.json"
else
  echo "Failed to fetch rooms and devices. HTTP status code: $HTTP_STATUS"
  rm "$TEMP_FILE"
fi
