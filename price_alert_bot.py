#!/usr/bin/env python3
"""
PriceAlertBot - Alerts when watched stocks drop below their recommended buy price.

Reads buy prices from buy_prices.json (populated by EarningsBot) and checks
current stock prices. Posts alerts to Discord when stocks are at or below
their "Buy Below" price.

Usage:
    python price_alert_bot.py              # Check all tracked stocks
    python price_alert_bot.py --test       # Test with sample data
    python price_alert_bot.py --dry-run    # Process but don't post to Discord
"""

import os
import sys
import re
import json
import argparse
from typing import Optional
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Configuration
FMP_API_KEY = os.getenv("FMP_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
FMP_STABLE_URL = "https://financialmodelingprep.com/stable"

BUY_PRICES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "buy_prices.json")


def load_buy_prices(filepath: str = BUY_PRICES_FILE) -> dict:
    """Load buy prices from JSON file."""
    if not os.path.exists(filepath):
        print(f"No buy prices file found at {filepath}")
        return {}

    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading buy prices file: {e}")
        return {}


def parse_price(price_str: str) -> Optional[float]:
    """Parse a dollar amount string like '$190.00' into a float."""
    match = re.search(r'\$?([\d,]+\.?\d*)', price_str)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def fetch_stock_quote(ticker: str) -> Optional[dict]:
    """Fetch real-time stock quote."""
    url = f"{FMP_STABLE_URL}/quote"
    params = {"symbol": ticker, "apikey": FMP_API_KEY}

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            return data[0]
        elif isinstance(data, dict):
            return data
        return None
    except requests.RequestException as e:
        print(f"Error fetching quote for {ticker}: {e}")
        return None


def create_alert_embed(ticker: str, current_price: float, buy_below: float, discount_pct: float, fiscal_period: str) -> dict:
    """Create a Discord embed for a price alert."""
    return {
        "title": f"🚨 {ticker} Price Alert",
        "description": f"**{ticker}** is trading below the recommended buy price!",
        "color": 0x00FF00,  # Green - buying opportunity
        "fields": [
            {
                "name": "💲 Current Price",
                "value": f"${current_price:.2f}",
                "inline": True
            },
            {
                "name": "🎯 Buy Below",
                "value": f"${buy_below:.2f}",
                "inline": True
            },
            {
                "name": "📉 Discount",
                "value": f"{discount_pct:.1f}% below target",
                "inline": True
            },
            {
                "name": "📊 Based On",
                "value": f"{fiscal_period} Earnings",
                "inline": False
            }
        ],
        "footer": {
            "text": "PriceAlertBot • Data from Financial Modeling Prep"
        }
    }


def create_summary_embed(total_alerts: int, total_tracked: int) -> dict:
    """Create a summary embed for price alerts."""
    return {
        "title": "🚨 Price Alert Summary",
        "description": f"**{total_alerts}** of **{total_tracked}** tracked stocks are below their Buy Below price",
        "color": 0x5865F2  # Discord blurple
    }


def process_alerts() -> list:
    """
    Check all tracked stocks against their buy prices.
    Returns list of embeds to post.
    """
    buy_prices = load_buy_prices()

    if not buy_prices:
        print("No buy prices tracked yet")
        return []

    print(f"Checking {len(buy_prices)} tracked stocks...")

    alerts = []

    for ticker, data in buy_prices.items():
        buy_price_str = data.get("buy_price", "")
        fiscal_period = data.get("fiscal_period", "Unknown")

        buy_below = parse_price(buy_price_str)
        if buy_below is None:
            print(f"  Skipping {ticker}: could not parse buy price '{buy_price_str}'")
            continue

        print(f"  Checking {ticker} (Buy Below: ${buy_below:.2f})...")
        quote = fetch_stock_quote(ticker)

        if not quote:
            print(f"  Could not fetch quote for {ticker}")
            continue

        current_price = quote.get("price")
        if current_price is None:
            print(f"  No price data for {ticker}")
            continue

        print(f"    Current: ${current_price:.2f} vs Buy Below: ${buy_below:.2f}")

        if current_price <= buy_below:
            discount_pct = ((buy_below - current_price) / buy_below) * 100
            print(f"    🚨 ALERT: {ticker} is {discount_pct:.1f}% below buy price!")
            alerts.append(create_alert_embed(
                ticker=ticker,
                current_price=current_price,
                buy_below=buy_below,
                discount_pct=discount_pct,
                fiscal_period=fiscal_period
            ))
        else:
            above_pct = ((current_price - buy_below) / buy_below) * 100
            print(f"    ✅ {ticker} is {above_pct:.1f}% above buy price")

    if not alerts:
        print("\nNo stocks below their Buy Below price")
        return []

    # Add summary at the beginning
    embeds = [create_summary_embed(len(alerts), len(buy_prices))]
    embeds.extend(alerts)

    return embeds


def post_to_discord(embeds: list) -> bool:
    """Post embeds to Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_URL not set")
        return False

    # Discord allows max 10 embeds per message
    for i in range(0, len(embeds), 10):
        batch = embeds[i:i+10]
        payload = {"embeds": batch}

        try:
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error posting to Discord: {e}")
            return False

    return True


def run_test():
    """Run with sample data to test Discord formatting."""
    print("Running test with sample data...")

    test_embeds = [
        create_summary_embed(2, 5),
        create_alert_embed(
            ticker="NFLX",
            current_price=845.50,
            buy_below=880.00,
            discount_pct=3.9,
            fiscal_period="Q4 2025"
        ),
        create_alert_embed(
            ticker="SHOP",
            current_price=92.30,
            buy_below=100.00,
            discount_pct=7.7,
            fiscal_period="Q3 2025"
        ),
    ]

    if post_to_discord(test_embeds):
        print("✅ Test embeds posted successfully!")
    else:
        print("❌ Failed to post test embeds")


def main():
    parser = argparse.ArgumentParser(description="PriceAlertBot - Buy price alerts")
    parser.add_argument("--test", action="store_true", help="Run with test data")
    parser.add_argument("--dry-run", action="store_true", help="Process but don't post to Discord")
    args = parser.parse_args()

    # Validate environment
    if not FMP_API_KEY:
        print("Error: FMP_API_KEY environment variable not set")
        sys.exit(1)

    if not DISCORD_WEBHOOK_URL and not args.dry_run:
        print("Error: DISCORD_WEBHOOK_URL environment variable not set")
        sys.exit(1)

    # Run test mode
    if args.test:
        run_test()
        return

    # Process alerts
    embeds = process_alerts()

    if not embeds:
        print("✅ No price alerts to post")
        return

    if args.dry_run:
        print(f"\n[DRY RUN] Would post {len(embeds)} embeds to Discord")
        for embed in embeds:
            print(f"  - {embed.get('title', 'No title')}")
        return

    # Post to Discord
    if post_to_discord(embeds):
        print(f"✅ Posted {len(embeds)} price alerts to Discord")
    else:
        print("❌ Failed to post price alerts")
        sys.exit(1)


if __name__ == "__main__":
    main()
