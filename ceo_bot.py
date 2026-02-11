#!/usr/bin/env python3
"""
CEO Trading Bot - Alerts for large stock purchases by company CEOs/insiders.

Uses Perplexity AI to search for recent CEO/insider purchases and posts
large buys to Discord.

Usage:
    python ceo_bot.py              # Check recent CEO purchases
    python ceo_bot.py --test       # Test with sample data
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
CEO_WEBHOOK_URL = os.getenv("CONGRESS_DISCORD_WEBHOOK_URL")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Minimum trade size to alert on (in dollars)
MIN_TRADE_SIZE = 100000


def strip_citations(text: str) -> str:
    """Remove citation references like [1], [2][3], etc. from text."""
    return re.sub(r'\[\d+\]', '', text).strip()


def fetch_insider_trades(days: int = 7) -> list:
    """
    Fetch recent CEO/insider purchases using Perplexity AI.
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
                    "content": f"""Find all significant stock PURCHASES (not sales) by company CEOs, CFOs, COOs, CTOs, or other C-suite executives disclosed between {from_date} and {to_date} that are worth $100,000 or more.

Look for insider buying activity reported in SEC Form 4 filings, financial news, and insider trading databases.

For each trade, provide in this EXACT JSON format (one trade per line):
{{"ticker": "AAPL", "executive": "Tim Cook", "title": "CEO", "company": "Apple Inc.", "value": "$500,000", "shares": "5,000", "trade_date": "2026-01-25"}}

Only include PURCHASES over $100,000 by C-suite executives. Return ONLY the JSON lines, no other text. If no trades found, return: NO_TRADES"""
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
        print(f"Error fetching insider trades: {e}")
        return []


def create_trade_embed(trade: dict) -> dict:
    """
    Create a Discord embed for a CEO purchase.
    """
    ticker = trade.get("ticker", "N/A")
    executive = trade.get("executive", "Unknown")
    title = trade.get("title", "Executive")
    company = trade.get("company", "")
    trade_date = trade.get("trade_date", "N/A")
    value = trade.get("value", "N/A")
    shares = trade.get("shares", "N/A")

    embed = {
        "title": f"👔 Insider Buy Alert: {ticker}",
        "description": f"**{executive}** ({title})\n{company}",
        "color": 0x00AA00,  # Green for insider buys
        "fields": [
            {
                "name": "💰 Value",
                "value": value,
                "inline": True
            },
            {
                "name": "📊 Shares",
                "value": shares,
                "inline": True
            },
            {
                "name": "📅 Trade Date",
                "value": trade_date,
                "inline": True
            }
        ],
        "footer": {
            "text": "InsiderBot • Data from Perplexity AI"
        }
    }

    return embed


def create_summary_embed(num_trades: int, total_executives: int) -> dict:
    """Create a summary embed for the week's insider purchases."""
    return {
        "title": "👔 Insider Trading Alert",
        "description": f"**{num_trades}** large purchases detected from **{total_executives}** executives in the last 7 days",
        "color": 0x00AA00,
        "footer": {
            "text": f"Minimum threshold: ${MIN_TRADE_SIZE:,}"
        }
    }


def post_to_discord(embeds: list) -> bool:
    """Post embeds to Discord webhook."""
    if not CEO_WEBHOOK_URL:
        print("Error: CONGRESS_DISCORD_WEBHOOK_URL not set")
        return False

    # Discord allows max 10 embeds per message
    for i in range(0, len(embeds), 10):
        batch = embeds[i:i+10]
        payload = {"embeds": batch}

        try:
            response = requests.post(
                CEO_WEBHOOK_URL,
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
    executive = trade.get("executive", "").lower().strip()
    ticker = trade.get("ticker", "").upper().strip()
    trade_date = trade.get("trade_date", "").strip()
    value = trade.get("value", "").strip()
    return f"{executive}|{ticker}|{trade_date}|{value}"


def load_posted_trades(filepath: str = "posted_insider_trades.json") -> set:
    """Load set of previously posted trade keys."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    return set()


def save_posted_trades(posted: set, filepath: str = "posted_insider_trades.json"):
    """Save posted trade keys, keeping only last 500 to prevent file growth."""
    posted_list = sorted(posted)[-500:]
    with open(filepath, "w") as f:
        json.dump(posted_list, f, indent=2)


def process_insider_purchases(days: int = 7) -> list:
    """
    Process insider purchases using Perplexity.
    Skips trades that have already been posted.
    Returns list of embeds to post.
    """
    print(f"Fetching insider purchases from the last {days} days...")

    trades = fetch_insider_trades(days)
    print(f"Found {len(trades)} large insider purchases (>${MIN_TRADE_SIZE:,})")

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
            print(f"  Skipping already posted: {trade.get('executive', '')} - {trade.get('ticker', '')}")

    print(f"New trades to post: {len(new_trades)} (skipped {len(trades) - len(new_trades)} duplicates)")

    if not new_trades:
        return []

    # Save updated posted trades
    save_posted_trades(posted)

    embeds = []

    # Get unique executives
    executives = set(t.get("executive", "") for t in new_trades)

    # Add summary
    if len(new_trades) > 1:
        embeds.append(create_summary_embed(len(new_trades), len(executives)))

    # Add individual trade embeds (limit to 9 to stay under Discord's 10 embed limit)
    for trade in new_trades[:9]:
        embeds.append(create_trade_embed(trade))

    return embeds


def run_test():
    """Run with sample data to test Discord formatting."""
    print("Running test with sample data...")

    test_embeds = [
        create_summary_embed(2, 2),
        {
            "title": "👔 Insider Buy Alert: NVDA",
            "description": "**Jensen Huang** (CEO)\nNVIDIA Corporation",
            "color": 0x00AA00,
            "fields": [
                {"name": "💰 Value", "value": "$2.50M", "inline": True},
                {"name": "📊 Shares", "value": "25,000", "inline": True},
                {"name": "📅 Trade Date", "value": "2026-01-25", "inline": True}
            ],
            "footer": {"text": "InsiderBot • Data from Perplexity AI"}
        },
        {
            "title": "👔 Insider Buy Alert: JPM",
            "description": "**Jamie Dimon** (CEO)\nJPMorgan Chase & Co.",
            "color": 0x00AA00,
            "fields": [
                {"name": "💰 Value", "value": "$1.00M", "inline": True},
                {"name": "📊 Shares", "value": "8,500", "inline": True},
                {"name": "📅 Trade Date", "value": "2026-01-24", "inline": True}
            ],
            "footer": {"text": "InsiderBot • Data from Perplexity AI"}
        }
    ]

    if post_to_discord(test_embeds):
        print("✅ Test embeds posted successfully!")
    else:
        print("❌ Failed to post test embeds")


def main():
    parser = argparse.ArgumentParser(description="InsiderBot - Discord alerts for insider purchases")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back (default: 7)")
    parser.add_argument("--test", action="store_true", help="Run with test data")
    parser.add_argument("--dry-run", action="store_true", help="Process but don't post to Discord")
    args = parser.parse_args()

    # Validate environment
    if not PERPLEXITY_API_KEY:
        print("Error: PERPLEXITY_API_KEY environment variable not set")
        sys.exit(1)

    if not CEO_WEBHOOK_URL and not args.dry_run and not args.test:
        print("Error: CONGRESS_DISCORD_WEBHOOK_URL environment variable not set")
        sys.exit(1)

    # Run test mode
    if args.test:
        run_test()
        return

    # Process purchases
    embeds = process_insider_purchases(args.days)

    if not embeds:
        print("✅ No large insider purchases found - nothing to post")
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
