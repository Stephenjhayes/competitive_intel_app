#!/usr/bin/env bash
# add_rules.sh — POST competitor rules to the Firehose tap
# Run this locally: bash add_rules.sh

TAP_TOKEN="fh_NqNwTUC0SPPPBEKqyo0vX17EdG49accC6DaICAoa"
BASE="https://api.firehose.com/v1/rules"

rule() {
  local value="$1" tag="$2"
  echo "Adding [$tag]: $value"
  curl -s -X POST \
    -H "Authorization: Bearer $TAP_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"value\": \"$value\", \"tag\": \"$tag\"}" \
    "$BASE" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  OK:', d.get('data',{}).get('id','?'))" 2>/dev/null || echo "  (check response above)"
  sleep 0.3
}

echo "=== Duck Creek Technologies ==="
rule '"Duck Creek Technologies"' "duck_creek"
rule 'title:"Duck Creek" AND recent:24h' "duck_creek"
rule '"Duck Creek Technologies insurance"' "duck_creek"

echo "=== Sapiens International ==="
rule '"Sapiens International"' "sapiens"
rule 'title:"Sapiens International" AND recent:24h' "sapiens"
rule '"Sapiens International insurance software"' "sapiens"

echo "=== Majesco ==="
rule '"Majesco"' "majesco"
rule '"Majesco insurance platform cloud"' "majesco"

echo "=== Insurity ==="
rule '"Insurity"' "insurity"
rule '"Insurity insurance software"' "insurity"

echo "=== Applied Systems ==="
rule '"Applied Systems"' "applied_systems"
rule 'title:"Applied Systems" AND recent:24h' "applied_systems"
rule '"Applied Systems insurance agency management"' "applied_systems"

echo "=== OneShield Software ==="
rule '"OneShield"' "one_shield"
rule '"OneShield insurance policy administration"' "one_shield"

echo ""
echo "Done. Verify at: https://firehose.com/dashboard"
