#!/usr/bin/env python3
"""Debug script to check transcript fetching and guidance extraction."""

import os
import requests
from dotenv import load_dotenv
import anthropic

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
FMP_STABLE_URL = "https://financialmodelingprep.com/stable"

print(f"FMP API Key: {FMP_API_KEY[:10]}...")
print(f"Anthropic API Key: {ANTHROPIC_API_KEY[:20]}...")

# Try to fetch META Q4 2025 transcript
ticker = "META"
year = 2025
quarter = 4

print(f"\n--- Fetching transcript for {ticker} Q{quarter} {year} ---")
url = f"{FMP_STABLE_URL}/earning-call-transcript"
params = {"symbol": ticker, "year": year, "quarter": quarter, "apikey": FMP_API_KEY}

response = requests.get(url, params=params, timeout=30)
print(f"Status code: {response.status_code}")

data = response.json()
print(f"Response type: {type(data)}")

if isinstance(data, list):
    print(f"List length: {len(data)}")
    if data:
        print(f"First item keys: {data[0].keys() if isinstance(data[0], dict) else 'not a dict'}")
        content = data[0].get("content", "")
        print(f"Content length: {len(content)} chars")
        if content:
            print(f"First 500 chars:\n{content[:500]}")
elif isinstance(data, dict):
    print(f"Dict keys: {data.keys()}")
    if "Error Message" in data:
        print(f"Error: {data['Error Message']}")
else:
    print(f"Raw response: {data}")

# If we got content, try Claude extraction
if isinstance(data, list) and data and data[0].get("content"):
    content = data[0]["content"]
    print(f"\n--- Testing Claude extraction ---")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Truncate if needed
    if len(content) > 30000:
        content = content[-30000:]

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=150,
            messages=[
                {
                    "role": "user",
                    "content": f"""Extract the forward guidance from this {ticker} earnings call transcript.
Focus on: revenue guidance, EPS guidance, growth expectations, or outlook for next quarter/year.
Return a concise 1-2 sentence summary. If no clear guidance is given, return "No specific guidance provided."

Transcript:
{content}"""
                }
            ]
        )
        guidance = message.content[0].text.strip()
        print(f"Claude response:\n{guidance}")
    except Exception as e:
        print(f"Claude error: {e}")
