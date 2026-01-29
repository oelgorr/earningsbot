#!/usr/bin/env python3
"""Debug Perplexity guidance extraction."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

def test_guidance(ticker, quarter, year):
    print(f"\n--- Testing {ticker} Q{quarter} {year} ---")

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "sonar",
        "messages": [
            {
                "role": "user",
                "content": f"""What is {ticker}'s forward guidance from their Q{quarter} {year} earnings report?

Focus on: revenue guidance, EPS guidance, growth expectations, or outlook for next quarter/year.
Return ONLY a concise 1-2 sentence summary of the guidance. No preamble or explanation.
If no specific guidance was provided, respond with exactly: NO_GUIDANCE"""
            }
        ],
        "max_tokens": 150
    }

    response = requests.post(
        PERPLEXITY_API_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    print(f"Status: {response.status_code}")
    data = response.json()

    if "choices" in data:
        guidance = data["choices"][0]["message"]["content"]
        print(f"Response:\n{guidance}")
    else:
        print(f"Full response:\n{data}")

# Test both
test_guidance("META", 4, 2025)
test_guidance("TSLA", 4, 2025)
