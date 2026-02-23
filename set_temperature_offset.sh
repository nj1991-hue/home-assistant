#!/bin/bash

# Usage: ./set_tado_device_offset.sh <home_id> <device_id> <offset>

HOME_ID="$1"
DEVICE_ID="$2"
OFFSET="$3"

if [ -z "$HOME_ID" ] || [ -z "$DEVICE_ID" ] || [ -z "$OFFSET" ]; then
  echo "Usage: $0 <home_id> <device_id> <offset>"
  exit 1
fi

# Temporary file to store the response
TEMP_FILE=$(mktemp)

# Make the request, capturing status code and storing body in TEMP_FILE
HTTP_STATUS=$(curl -s -w "%{http_code}" -o "$TEMP_FILE" \
  "https://hops.tado.com/homes/${HOME_ID}/roomsAndDevices/devices/${DEVICE_ID}?ngsw-bypass=true" \
  -X PATCH \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0" \
  -H "Accept: application/json, text/plain, */*" \
  -H "Accept-Language: it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3" \
  -H "Accept-Encoding: gzip, deflate, br, zstd" \
  -H "Content-Type: application/json" \
  -H "Referer: https://app.tado.com/" \
  -H "X-Amzn-Trace-Id: tado=webapp-2025.3.6.10.51-release/v3676" \
  -H "Origin: https://app.tado.com" \
  -H "Sec-Fetch-Dest: empty" \
  -H "Sec-Fetch-Mode: cors" \
  -H "Sec-Fetch-Site: same-site" \
  -H "Authorization: Bearer $(jq -r '.access_token' /config/tado_response.json)" \
  -H "Connection: keep-alive" \
  -H "Priority: u=0" \
  -H "TE: trailers" \
  --data-raw "{\"temperatureOffset\":${OFFSET}}")

# Check if the HTTP status code is 200 or 204 (PATCH often returns 204 No Content)
if [ "$HTTP_STATUS" -eq 200 ] || [ "$HTTP_STATUS" -eq 204 ]; then
  mv "$TEMP_FILE" "/config/tado_device_${DEVICE_ID}_offset_response.json"
else
  echo "Failed to set device offset. HTTP status code: $HTTP_STATUS"
  cat "$TEMP_FILE"
  rm "$TEMP_FILE"
fi
