#!/usr/bin/env python3
"""
Congress Trading Bot - Alerts for large stock purchases by Congress members.

Uses Perplexity AI to search for recent congressional trades and posts
large purchases to Discord.

Usage:
    python congress_bot.py              # Check recent trades
    python congress_bot.py --test       # Test with sample data
"""

import os
import sys
import re
import argparse
import json
from datetime import datetime, timedelta
from typing import Optional
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Configuration
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
CONGRESS_WEBHOOK_URL = os.getenv("CONGRESS_DISCORD_WEBHOOK_URL")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Minimum trade size to alert on (in dollars)
MIN_TRADE_SIZE = 100000


def strip_citations(text: str) -> str:
    """Remove citation references like [1], [2][3], etc. from text."""
    return re.sub(r'\[\d+\]', '', text).strip()


def fetch_congress_trades_perplexity(days: int = 7) -> list:
    """
    Fetch recent congressional trades using Perplexity AI.
    Returns a list of trade dictionaries.
    """
    if not PERPLEXITY_API_KEY:
        return []

    try:
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }

        from_date = (datetime.now() - timedelta(days=days)).strftime("%B %d, %Y")
        to_date = datetime.now().strftime("%B %d, %Y")

        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "user",
                    "content": f"""Find all stock PURCHASES (not sales) by US Congress members disclosed between {from_date} and {to_date} that are worth $100,000 or more.

For each trade, provide in this EXACT JSON format (one trade per line):
{{"ticker": "AAPL", "politician": "Nancy Pelosi", "party": "D", "chamber": "House", "amount": "$100,001 - $250,000", "trade_date": "2026-01-25", "disclosure_date": "2026-01-28"}}

Only include PURCHASES over $100,000. Return ONLY the JSON lines, no other text. If no trades found, return: NO_TRADES"""
                }
            ],
            "max_tokens": 1000
        }

        response = requests.post(
            PERPLEXITY_API_URL,
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()

        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        content = strip_citations(content)

        if "NO_TRADES" in content.upper():
            return []

        # Parse JSON lines
        trades = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    trade = json.loads(line)
                    trades.append(trade)
                except json.JSONDecodeError:
                    continue

        return trades

    except Exception as e:
        print(f"Error fetching Congress trades: {e}")
        return []


def create_trade_embed(trade: dict) -> dict:
    """
    Create a Discord embed for a congressional trade.
    """
    ticker = trade.get("ticker", "N/A")
    politician = trade.get("politician", "Unknown")
    chamber = trade.get("chamber", "")
    party = trade.get("party", "")
    trade_date = trade.get("trade_date", "N/A")
    disclosure_date = trade.get("disclosure_date", "N/A")
    amount = trade.get("amount", "N/A")

    # Party emoji
    party_emoji = "🔵" if party == "D" else "🔴" if party == "R" else "⚪"

    # Chamber label
    chamber_label = "Senator" if chamber == "Senate" else "Rep." if chamber == "House" else ""

    embed = {
        "title": f"🏛️ Congress Buy Alert: {ticker}",
        "description": f"{party_emoji} **{chamber_label} {politician}** ({party})",
        "color": 0x5865F2,  # Discord blurple
        "fields": [
            {
                "name": "💰 Amount",
                "value": amount,
                "inline": True
            },
            {
                "name": "📅 Trade Date",
                "value": trade_date,
                "inline": True
            },
            {
                "name": "📋 Disclosed",
                "value": disclosure_date,
                "inline": True
            }
        ],
        "footer": {
            "text": "CongressBot • Data from Perplexity AI"
        }
    }

    return embed


def create_summary_embed(num_trades: int, total_politicians: int) -> dict:
    """Create a summary embed for the day's Congress trades."""
    return {
        "title": "🏛️ Congress Trading Alert",
        "description": f"**{num_trades}** large purchases detected from **{total_politicians}** politicians in the last 7 days",
        "color": 0x5865F2,
        "footer": {
            "text": f"Minimum threshold: ${MIN_TRADE_SIZE:,}"
        }
    }


def post_to_discord(embeds: list) -> bool:
    """Post embeds to Discord webhook."""
    if not CONGRESS_WEBHOOK_URL:
        print("Error: CONGRESS_DISCORD_WEBHOOK_URL not set")
        return False

    # Discord allows max 10 embeds per message
    for i in range(0, len(embeds), 10):
        batch = embeds[i:i+10]
        payload = {"embeds": batch}

        try:
            response = requests.post(
                CONGRESS_WEBHOOK_URL,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error posting to Discord: {e}")
            return False

    return True


def get_trade_key(trade: dict) -> str:
    """Generate a unique key for a trade to track duplicates."""
    politician = trade.get("politician", "").lower().strip()
    ticker = trade.get("ticker", "").upper().strip()
    trade_date = trade.get("trade_date", "").strip()
    amount = trade.get("amount", "").strip()
    return f"{politician}|{ticker}|{trade_date}|{amount}"


def load_posted_trades(filepath: str = "posted_congress_trades.json") -> set:
    """Load set of previously posted trade keys."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    return set()


def save_posted_trades(posted: set, filepath: str = "posted_congress_trades.json"):
    """Save posted trade keys, keeping only last 500 to prevent file growth."""
    posted_list = sorted(posted)[-500:]
    with open(filepath, "w") as f:
        json.dump(posted_list, f, indent=2)


def process_congress_trades(days: int = 7) -> list:
    """
    Process congressional trades for a date range.
    Skips trades that have already been posted.
    Returns list of embeds to post.
    """
    print(f"Fetching Congress trades from the last {days} days...")

    trades = fetch_congress_trades_perplexity(days)
    print(f"Found {len(trades)} large purchases (>${MIN_TRADE_SIZE:,})")

    if not trades:
        return []

    # Filter out already-posted trades
    posted = load_posted_trades()
    new_trades = []
    for trade in trades:
        key = get_trade_key(trade)
        if key not in posted:
            new_trades.append(trade)
            posted.add(key)
        else:
            print(f"  Skipping already posted: {trade.get('politician', '')} - {trade.get('ticker', '')}")

    print(f"New trades to post: {len(new_trades)} (skipped {len(trades) - len(new_trades)} duplicates)")

    if not new_trades:
        return []

    # Save updated posted trades
    save_posted_trades(posted)

    embeds = []

    # Get unique politicians
    politicians = set(t.get("politician", "") for t in new_trades)

    # Add summary
    if len(new_trades) > 1:
        embeds.append(create_summary_embed(len(new_trades), len(politicians)))

    # Add individual trade embeds
    for trade in new_trades:
        embeds.append(create_trade_embed(trade))

    return embeds


def run_test():
    """Run with sample data to test Discord formatting."""
    print("Running test with sample data...")

    test_embeds = [
        create_summary_embed(2, 2),
        {
            "title": "🏛️ Congress Buy Alert: NVDA",
            "description": "🔵 **Rep. Nancy Pelosi** (D)",
            "color": 0x5865F2,
            "fields": [
                {"name": "💰 Amount", "value": "$500,001 - $1,000,000", "inline": True},
                {"name": "📅 Trade Date", "value": "2026-01-25", "inline": True},
                {"name": "📋 Disclosed", "value": "2026-01-28", "inline": True}
            ],
            "footer": {"text": "CongressBot • Data from Perplexity AI"}
        },
        {
            "title": "🏛️ Congress Buy Alert: AAPL",
            "description": "🔴 **Sen. Tommy Tuberville** (R)",
            "color": 0x5865F2,
            "fields": [
                {"name": "💰 Amount", "value": "$100,001 - $250,000", "inline": True},
                {"name": "📅 Trade Date", "value": "2026-01-24", "inline": True},
                {"name": "📋 Disclosed", "value": "2026-01-28", "inline": True}
            ],
            "footer": {"text": "CongressBot • Data from Perplexity AI"}
        }
    ]

    if post_to_discord(test_embeds):
        print("✅ Test embeds posted successfully!")
    else:
        print("❌ Failed to post test embeds")


def main():
    parser = argparse.ArgumentParser(description="CongressBot - Discord alerts for Congress trades")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back (default: 7)")
    parser.add_argument("--test", action="store_true", help="Run with test data")
    parser.add_argument("--dry-run", action="store_true", help="Process but don't post to Discord")
    args = parser.parse_args()

    # Validate environment
    if not PERPLEXITY_API_KEY:
        print("Error: PERPLEXITY_API_KEY environment variable not set")
        sys.exit(1)

    if not CONGRESS_WEBHOOK_URL and not args.dry_run and not args.test:
        print("Error: CONGRESS_DISCORD_WEBHOOK_URL environment variable not set")
        sys.exit(1)

    # Run test mode
    if args.test:
        run_test()
        return

    # Process trades
    embeds = process_congress_trades(args.days)

    if not embeds:
        print("✅ No large Congress purchases found - nothing to post")
        return

    if args.dry_run:
        print(f"\n[DRY RUN] Would post {len(embeds)} embeds to Discord")
        for embed in embeds:
            print(f"  - {embed.get('title', 'No title')}")
        return

    # Post to Discord
    if post_to_discord(embeds):
        print(f"✅ Posted {len(embeds)} embeds to Discord")
    else:
        print("❌ Failed to post to Discord")
        sys.exit(1)


if __name__ == "__main__":
    main()
