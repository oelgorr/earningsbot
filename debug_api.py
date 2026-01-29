#!/usr/bin/env python3
"""Quick debug script to see what the FMP API returns."""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")
FMP_STABLE_URL = "https://financialmodelingprep.com/stable"

# Fetch earnings calendar for Jan 28
url = f"{FMP_STABLE_URL}/earnings-calendar"
params = {"from": "2026-01-28", "to": "2026-01-28", "apikey": FMP_API_KEY}

response = requests.get(url, params=params, timeout=30)
data = response.json()

# Find META in the results
for item in data:
    if item.get("symbol") == "META":
        print("META earnings data from API:")
        print(json.dumps(item, indent=2))
        break
else:
    print("META not found. First item in response:")
    if data:
        print(json.dumps(data[0], indent=2))
