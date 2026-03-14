"""
Quick smoke test for the Firehose API.

Usage:
    FIREHOSE_MGMT_KEY=fhm_... python test_firehose.py

Or with a .env file in place:
    python test_firehose.py
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

FIREHOSE_API_BASE = "https://api.firehose.com/v1"
MGMT_KEY = os.getenv("FIREHOSE_MGMT_KEY", "")

if not MGMT_KEY or MGMT_KEY == "fhm_...":
    sys.exit("ERROR: Set FIREHOSE_MGMT_KEY in .env or as an env var (starts with fhm_)")

headers = {"Authorization": f"Bearer {MGMT_KEY}", "Content-Type": "application/json"}


def check(label: str, resp: requests.Response) -> dict:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Status: {resp.status_code}")
    try:
        data = resp.json()
        print(f"  Response: {json.dumps(data, indent=2)[:800]}")
        resp.raise_for_status()
        return data
    except requests.HTTPError:
        print("  FAILED")
        sys.exit(1)


# 1. List existing taps
print("Testing Firehose API with your management key...")
resp = requests.get(f"{FIREHOSE_API_BASE}/taps", headers=headers, timeout=15)
taps_data = check("GET /v1/taps — list your taps", resp)

taps = taps_data.get("data", [])
print(f"\n  Found {len(taps)} existing tap(s).")

if taps:
    tap = taps[0]
    tap_token = tap.get("token") or tap.get("tap_token") or tap.get("fh_token", "")
    tap_name = tap.get("name", "unknown")
    print(f"  Using existing tap: '{tap_name}'")

    # 2. List rules on first tap
    if tap_token:
        tap_headers = {"Authorization": f"Bearer {tap_token}", "Content-Type": "application/json"}
        resp2 = requests.get(f"{FIREHOSE_API_BASE}/rules", headers=tap_headers, timeout=15)
        rules_data = check(f"GET /v1/rules — rules on tap '{tap_name}'", resp2)
        rules = rules_data.get("data", [])
        print(f"\n  Found {len(rules)} rule(s) on this tap.")
    else:
        print("  (No tap token available to list rules)")
else:
    print("\n  No taps yet — run `python main.py --bootstrap` to create one.")

print("\n\nAll checks passed. Your Firehose management key is working!")
