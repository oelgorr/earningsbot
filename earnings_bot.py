#!/usr/bin/env python3
"""
EarningsBot - Automated Discord earnings report notifications.

This script fetches earnings data for watched companies and posts
formatted summaries to Discord via webhook.

Usage:
    python earnings_bot.py              # Check yesterday's earnings
    python earnings_bot.py --date 2025-01-28  # Check specific date
    python earnings_bot.py --test       # Test with sample data
"""

import os
import sys
import re
import argparse
from datetime import datetime, timedelta
from typing import Optional
import requests
from dotenv import load_dotenv
import pytz


def strip_citations(text: str) -> str:
    """Remove citation references like [1], [2][3], etc. from text."""
    return re.sub(r'\[\d+\]', '', text).strip()

from config import WATCHED_TICKERS, TIMEZONE
from discord_formatter import (
    create_earnings_embed,
    create_summary_embed,
    create_no_earnings_embed
)

# Load environment variables from .env file
load_dotenv()

# API Configuration
FMP_API_KEY = os.getenv("FMP_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
FMP_STABLE_URL = "https://financialmodelingprep.com/stable"
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


def get_yesterday_date() -> str:
    """Get yesterday's date in YYYY-MM-DD format, accounting for timezone."""
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    yesterday = now - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def fetch_earnings_calendar(date: str) -> list:
    """
    Fetch earnings calendar for a specific date.
    Returns list of companies that reported earnings.
    Uses the new stable API endpoint.
    """
    url = f"{FMP_STABLE_URL}/earnings-calendar"
    params = {
        "from": date,
        "to": date,
        "apikey": FMP_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching earnings calendar: {e}")
        return []


def fetch_company_profile(ticker: str) -> Optional[dict]:
    """Fetch company profile for name and details."""
    # Try stable API first, fall back to legacy
    url = f"{FMP_STABLE_URL}/profile"
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
        print(f"Error fetching profile for {ticker}: {e}")
        return None


def fetch_earnings_history(ticker: str, limit: int = 4) -> list:
    """Fetch historical earnings for YoY comparison. Requires higher FMP plan."""
    # Skip this call entirely - requires paid plan
    # Uncomment below if you upgrade your FMP subscription
    return []
    # url = f"{FMP_STABLE_URL}/earnings"
    # params = {"symbol": ticker, "limit": limit, "apikey": FMP_API_KEY}
    # try:
    #     response = requests.get(url, params=params, timeout=30)
    #     response.raise_for_status()
    #     return response.json()
    # except requests.RequestException:
    #     return []


def fetch_earnings_guidance(ticker: str, year: int, quarter: int) -> Optional[str]:
    """
    Fetch earnings guidance using Perplexity AI to search recent news.
    Much more cost-effective than FMP transcripts (~$0.006 per query).
    """
    if not PERPLEXITY_API_KEY:
        return None

    try:
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
        response.raise_for_status()

        data = response.json()
        guidance = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        guidance = strip_citations(guidance)

        # Return default message if no guidance found
        if not guidance or "NO_GUIDANCE" in guidance.upper():
            return "No guidance provided"

        return guidance

    except Exception as e:
        print(f"  Error fetching guidance for {ticker}: {e}")
        return None


def fetch_key_takeaways(ticker: str, year: int, quarter: int) -> Optional[list]:
    """
    Fetch 3 key takeaways from earnings report using Perplexity AI.
    """
    if not PERPLEXITY_API_KEY:
        return None

    try:
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "user",
                    "content": f"""What are the 3 most important takeaways from {ticker}'s Q{quarter} {year} earnings report?

Focus on: significant business developments, growth metrics, challenges, strategic initiatives, or notable commentary.
Return ONLY 3 bullet points, each 1 sentence. No preamble, numbering, or explanation.
Format exactly like:
• First takeaway
• Second takeaway
• Third takeaway"""
                }
            ],
            "max_tokens": 250
        }

        response = requests.post(
            PERPLEXITY_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        # Parse bullet points and strip citations
        takeaways = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("•") or line.startswith("-") or line.startswith("*"):
                takeaway = line.lstrip("•-* ").strip()
                takeaway = strip_citations(takeaway)
                if takeaway:
                    takeaways.append(takeaway)

        return takeaways[:3] if takeaways else None

    except Exception as e:
        print(f"  Error fetching takeaways for {ticker}: {e}")
        return None


def get_previous_year_earnings(ticker: str, current_quarter: str) -> Optional[dict]:
    """Get the same quarter from previous year for YoY comparison."""
    history = fetch_earnings_history(ticker, limit=8)

    for earning in history:
        # Match fiscal quarter from previous year
        if earning.get("fiscalDateEnding"):
            earning_date = earning.get("fiscalDateEnding", "")
            # Simple matching - could be improved
            if earning_date and len(history) >= 5:
                # The 5th entry should be roughly same quarter last year
                return history[4] if len(history) > 4 else None

    return None


def filter_watched_earnings(earnings_calendar: list) -> list:
    """Filter earnings calendar to only include watched tickers."""
    watched_set = set(ticker.upper() for ticker in WATCHED_TICKERS)
    return [e for e in earnings_calendar if e.get("symbol", "").upper() in watched_set]


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


def process_earnings(date: str) -> tuple[list, int, int]:
    """
    Process earnings for a given date.
    Returns (embeds, beats, misses).
    """
    print(f"Fetching earnings for {date}...")

    # Get earnings calendar
    calendar = fetch_earnings_calendar(date)
    print(f"Found {len(calendar)} total earnings reports")

    # Filter to watched tickers
    watched_earnings = filter_watched_earnings(calendar)
    print(f"Found {len(watched_earnings)} watched companies")

    if not watched_earnings:
        return [], 0, 0  # Return empty - don't post if no watched companies reported

    embeds = []
    total_beats = 0
    total_misses = 0

    for earning in watched_earnings:
        ticker = earning.get("symbol", "")
        print(f"Processing {ticker}...")

        # Get company name
        profile = fetch_company_profile(ticker)
        company_name = profile.get("companyName", ticker) if profile else ticker

        # Get earnings data (stable API field names)
        eps_actual = earning.get("epsActual")
        eps_estimate = earning.get("epsEstimated")
        revenue_actual = earning.get("revenueActual")
        revenue_estimate = earning.get("revenueEstimated")

        # Get previous year data for YoY comparison (optional - requires higher plan)
        try:
            prev_year = get_previous_year_earnings(ticker, earning.get("fiscalDateEnding", ""))
            revenue_previous = prev_year.get("revenue") if prev_year else None
            eps_previous = prev_year.get("eps") if prev_year else None
        except Exception:
            revenue_previous = None
            eps_previous = None

        # Determine fiscal period from announcement date
        announcement_date = earning.get("date", "")
        quarter, year = None, None
        if announcement_date:
            try:
                dt = datetime.strptime(announcement_date, "%Y-%m-%d")
                # Earnings announced in Jan-Feb = Q4 of previous year
                # Mar-Apr = Q1, May-Jul = Q2, Aug-Oct = Q3, Nov-Dec = Q4
                month = dt.month
                if month <= 2:
                    quarter, year = 4, dt.year - 1
                elif month <= 5:
                    quarter, year = 1, dt.year
                elif month <= 8:
                    quarter, year = 2, dt.year
                elif month <= 11:
                    quarter, year = 3, dt.year
                else:
                    quarter, year = 4, dt.year
                fiscal_period = f"Q{quarter} {year}"
            except ValueError:
                fiscal_period = "Latest"
        else:
            fiscal_period = "Latest"

        # Get guidance and takeaways using Perplexity AI
        guidance = None
        takeaways = None
        if PERPLEXITY_API_KEY and year and quarter:
            print(f"  Fetching guidance for {ticker}...")
            guidance = fetch_earnings_guidance(ticker, year, quarter)
            print(f"  Fetching takeaways for {ticker}...")
            takeaways = fetch_key_takeaways(ticker, year, quarter)

        # Count beats/misses
        if eps_actual is not None and eps_estimate is not None:
            if eps_actual > eps_estimate:
                total_beats += 1
            elif eps_actual < eps_estimate:
                total_misses += 1

        # Create embed
        embed = create_earnings_embed(
            ticker=ticker,
            company_name=company_name,
            fiscal_period=fiscal_period,
            revenue_actual=revenue_actual,
            revenue_estimate=revenue_estimate,
            revenue_previous=revenue_previous,
            eps_actual=eps_actual,
            eps_estimate=eps_estimate,
            eps_previous=eps_previous,
            guidance=guidance,
            takeaways=takeaways
        )
        embeds.append(embed)

    # Add summary embed at the beginning
    if len(embeds) > 1:
        summary = create_summary_embed(len(embeds), total_beats, total_misses)
        embeds.insert(0, summary)

    return embeds, total_beats, total_misses


def run_test():
    """Run with sample data to test Discord formatting."""
    print("Running test with sample data...")

    test_embeds = [
        create_summary_embed(3, 2, 1),
        create_earnings_embed(
            ticker="AAPL",
            company_name="Apple Inc.",
            fiscal_period="Q4 2025",
            revenue_actual=94_930_000_000,
            revenue_estimate=94_500_000_000,
            revenue_previous=89_500_000_000,
            eps_actual=1.64,
            eps_estimate=1.60,
            eps_previous=1.46,
            guidance="Q1 2026 revenue expected between $118B-$122B"
        ),
        create_earnings_embed(
            ticker="MSFT",
            company_name="Microsoft Corporation",
            fiscal_period="Q2 2026",
            revenue_actual=62_020_000_000,
            revenue_estimate=61_500_000_000,
            revenue_previous=56_200_000_000,
            eps_actual=2.93,
            eps_estimate=2.89,
            eps_previous=2.69,
            guidance=None
        ),
        create_earnings_embed(
            ticker="NFLX",
            company_name="Netflix, Inc.",
            fiscal_period="Q4 2025",
            revenue_actual=9_370_000_000,
            revenue_estimate=9_500_000_000,
            revenue_previous=8_830_000_000,
            eps_actual=4.11,
            eps_estimate=4.45,
            eps_previous=3.89,
            guidance="Q1 2026 subscriber growth to slow"
        ),
    ]

    if post_to_discord(test_embeds):
        print("✅ Test embeds posted successfully!")
    else:
        print("❌ Failed to post test embeds")


def main():
    parser = argparse.ArgumentParser(description="EarningsBot - Discord earnings notifications")
    parser.add_argument("--date", help="Specific date to check (YYYY-MM-DD)", default=None)
    parser.add_argument("--test", action="store_true", help="Run with test data")
    parser.add_argument("--dry-run", action="store_true", help="Process but don't post to Discord")
    args = parser.parse_args()

    # Validate environment
    if not FMP_API_KEY:
        print("Error: FMP_API_KEY environment variable not set")
        print("Sign up at https://financialmodelingprep.com/developer")
        sys.exit(1)

    if not DISCORD_WEBHOOK_URL and not args.dry_run:
        print("Error: DISCORD_WEBHOOK_URL environment variable not set")
        sys.exit(1)

    # Run test mode
    if args.test:
        run_test()
        return

    # Determine date to check
    check_date = args.date or get_yesterday_date()
    print(f"Checking earnings for: {check_date}")

    # Process earnings
    embeds, beats, misses = process_earnings(check_date)

    # Skip if no watched companies reported
    if not embeds:
        print("✅ No watched companies reported earnings today - nothing to post")
        return

    if args.dry_run:
        print(f"\n[DRY RUN] Would post {len(embeds)} embeds to Discord")
        print(f"Beats: {beats}, Misses: {misses}")
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
