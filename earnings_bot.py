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
import json
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


def fetch_stock_quote(ticker: str) -> Optional[dict]:
    """
    Fetch real-time stock quote including pre/post market data.
    Returns dict with price, change, changesPercentage, etc.
    """
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


def fetch_recommended_buy_price(ticker: str, year: int, quarter: int, current_price: Optional[float] = None) -> Optional[str]:
    """
    Fetch a recommended buy price using Perplexity AI after earnings report.
    Considers earnings results, growth, valuation, and forward guidance.
    """
    if not PERPLEXITY_API_KEY:
        return None

    try:
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }

        price_context = f"The stock currently trades at ${current_price:.2f}. " if current_price else ""

        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "user",
                    "content": f"""Based on {ticker}'s Q{quarter} {year} earnings results, what is the maximum price you would recommend buying at?

{price_context}Consider the earnings results, revenue growth, EPS trends, forward guidance, and valuation.
Return ONLY a single price number (e.g. "$150.00"). No range, no explanation, no preamble, no disclaimers. Just the price."""
                }
            ],
            "max_tokens": 50
        }

        response = requests.post(
            PERPLEXITY_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        buy_price = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        buy_price = strip_citations(buy_price)

        if not buy_price or len(buy_price) > 50:
            return None

        return buy_price

    except Exception as e:
        print(f"  Error fetching buy price for {ticker}: {e}")
        return None


def check_all_time_high(ticker: str, date: str) -> bool:
    """
    Check if stock hit an all-time high on the given date using Perplexity.
    """
    if not PERPLEXITY_API_KEY:
        return False

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
                    "content": f"""Did {ticker} stock reach an all-time high on or around {date}?
Answer ONLY with YES or NO. Nothing else."""
                }
            ],
            "max_tokens": 10
        }

        response = requests.post(
            PERPLEXITY_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        answer = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()

        return "YES" in answer

    except Exception as e:
        print(f"  Error checking ATH for {ticker}: {e}")
        return False


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


def fetch_earnings_data_perplexity(ticker: str, date: str) -> dict:
    """
    Fetch actual earnings numbers (EPS, revenue) via Perplexity AI
    for tickers that FMP's free plan missed.
    Returns dict with epsActual, epsEstimated, revenueActual, revenueEstimated.
    """
    if not PERPLEXITY_API_KEY:
        return {}

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
                    "content": f"""What were {ticker}'s earnings results reported on {date}?

I need these 4 numbers:
1. Actual EPS (adjusted/non-GAAP)
2. Estimated EPS (analyst consensus)
3. Actual revenue
4. Estimated revenue

Return ONLY in this exact format (numbers only, revenue in dollars):
EPS_ACTUAL: 0.55
EPS_ESTIMATED: 0.50
REVENUE_ACTUAL: 900000000
REVENUE_ESTIMATED: 880000000

No explanations. Just the 4 lines."""
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
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        content = strip_citations(content)
        print(f"  Perplexity earnings data for {ticker}: {content}")

        result = {}
        for line in content.split("\n"):
            line = line.strip()
            try:
                if "EPS_ACTUAL" in line.upper():
                    val = re.search(r'[-]?[\d.]+', line.split(":")[-1])
                    if val:
                        result["epsActual"] = float(val.group())
                elif "EPS_ESTIMATED" in line.upper():
                    val = re.search(r'[-]?[\d.]+', line.split(":")[-1])
                    if val:
                        result["epsEstimated"] = float(val.group())
                elif "REVENUE_ACTUAL" in line.upper():
                    val = re.search(r'[\d.]+', line.split(":")[-1].replace(",", ""))
                    if val:
                        result["revenueActual"] = float(val.group())
                elif "REVENUE_ESTIMATED" in line.upper():
                    val = re.search(r'[\d.]+', line.split(":")[-1].replace(",", ""))
                    if val:
                        result["revenueEstimated"] = float(val.group())
            except (ValueError, IndexError):
                continue

        return result

    except Exception as e:
        print(f"  Error fetching earnings data for {ticker}: {e}")
        return {}


def verify_earnings_date_perplexity(ticker: str, date: str) -> bool:
    """
    Verify with Perplexity that a specific ticker actually reported earnings on a date.
    Uses two checks:
    1. Ask for the actual earnings date and compare (most reliable)
    2. If the date returned is old (Perplexity index lag), try a direct YES/NO as backup
    Only confirms if at least one check passes AND the earnings data query succeeds.
    """
    if not PERPLEXITY_API_KEY:
        return False

    try:
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }

        # Step 1: Ask for the actual most recent earnings date
        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "user",
                    "content": f"""What date did {ticker} most recently report its quarterly earnings results?
Return ONLY the date in YYYY-MM-DD format. Nothing else."""
                }
            ],
            "max_tokens": 20
        }

        response = requests.post(
            PERPLEXITY_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        answer = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        answer = strip_citations(answer)

        # Extract date from response
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', answer)
        if date_match:
            reported_date = date_match.group(1)
            if reported_date == date:
                print(f"    {ticker}: confirmed earnings on {date}")
                return True

            # If Perplexity returned an old date (index lag for today's earnings),
            # check if the returned date is significantly before our target date
            try:
                target = datetime.strptime(date, "%Y-%m-%d")
                returned = datetime.strptime(reported_date, "%Y-%m-%d")
                days_diff = (target - returned).days

                # If the last known earnings was 30-120 days ago, this ticker
                # could be reporting again now (quarterly cadence)
                if 30 <= days_diff <= 120:
                    # Do a YES/NO backup check with very specific prompt
                    backup_payload = {
                        "model": "sonar",
                        "messages": [
                            {
                                "role": "user",
                                "content": f"""Did {ticker} release its quarterly earnings report on exactly {date}?
I know their previous earnings were on {reported_date}. I am asking specifically about {date}.
If you cannot confirm earnings were released on exactly {date}, answer NO.
Answer ONLY YES or NO."""
                            }
                        ],
                        "max_tokens": 10
                    }
                    backup_response = requests.post(
                        PERPLEXITY_API_URL,
                        headers=headers,
                        json=backup_payload,
                        timeout=30
                    )
                    backup_response.raise_for_status()
                    backup_answer = backup_response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
                    backup_answer = strip_citations(backup_answer)
                    if "YES" in backup_answer:
                        print(f"    {ticker}: backup check confirmed earnings on {date} (last known: {reported_date})")
                        return True
            except ValueError:
                pass

        return False

    except Exception as e:
        print(f"  Error verifying earnings date for {ticker}: {e}")
        return False


def fetch_missing_earnings_perplexity(date: str, already_found: list) -> list:
    """
    Use Perplexity AI to find watched tickers that reported earnings on a date
    but were missing from FMP's calendar (free plan has incomplete data).
    Uses a two-step process: bulk query for candidates, then individual verification.
    Returns list of dicts matching FMP calendar format for any confirmed tickers.
    """
    if not PERPLEXITY_API_KEY:
        return []

    # Determine which watched tickers FMP already found
    found_set = set(e.get("symbol", "").upper() for e in already_found)
    missing_tickers = [t for t in WATCHED_TICKERS if t.upper() not in found_set]

    if not missing_tickers:
        return []

    ticker_list = ", ".join(missing_tickers)

    try:
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }

        # Verify each missing ticker individually
        # Individual queries are most reliable (~$0.001 each, ~$0.05 total)
        print(f"  Checking {len(missing_tickers)} tickers individually...")
        all_found = []

        for ticker in missing_tickers:
            if verify_earnings_date_perplexity(ticker, date):
                # Fetch actual earnings numbers to confirm and populate data
                print(f"  Fetching earnings data for {ticker} via Perplexity...")
                earnings_data = fetch_earnings_data_perplexity(ticker, date)

                # Only include if we got at least EPS actual data
                # This filters out false positives where Perplexity can't find real data
                if earnings_data.get("epsActual") is not None:
                    print(f"  ✅ {ticker} confirmed with data - reported on {date}")
                    all_found.append({
                        "symbol": ticker,
                        "date": date,
                        "epsActual": earnings_data.get("epsActual"),
                        "epsEstimated": earnings_data.get("epsEstimated"),
                        "revenueActual": earnings_data.get("revenueActual"),
                        "revenueEstimated": earnings_data.get("revenueEstimated"),
                    })
                else:
                    print(f"  ⚠️ {ticker} - could not fetch earnings data, skipping")

        return all_found

    except Exception as e:
        print(f"  Error in Perplexity earnings check: {e}")
        return []


def fetch_missing_weekly_earnings_perplexity(start_date: str, end_date: str, already_found: list) -> list:
    """
    Use Perplexity AI to find watched tickers reporting earnings during a week
    that were missing from FMP's calendar.
    Returns list of dicts matching FMP calendar format.
    """
    if not PERPLEXITY_API_KEY:
        return []

    found_set = set(e.get("symbol", "").upper() for e in already_found)
    missing_tickers = [t for t in WATCHED_TICKERS if t.upper() not in found_set]

    if not missing_tickers:
        return []

    ticker_list = ", ".join(missing_tickers)

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
                    "content": f"""Which of these stocks are scheduled to report their quarterly earnings between {start_date} and {end_date} (inclusive)?

{ticker_list}

Search for each ticker's next earnings date. Only include tickers with earnings dates that fall within {start_date} to {end_date}.
For each match, return the format: TICKER:YYYY-MM-DD (one per line).
If none of them report during this period, respond with: NONE"""
                }
            ],
            "max_tokens": 500
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
        content = strip_citations(content)
        print(f"  Perplexity weekly response: {content}")

        if "NONE" in content.upper() and len(content) < 20:
            return []

        # Parse TICKER:DATE format from response
        all_found = []
        watched_upper = set(t.upper() for t in missing_tickers)

        for line in content.split("\n"):
            line = line.strip().lstrip("•-*0123456789.) ")
            # Try to extract a ticker and date from each line
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
            if not date_match:
                continue
            report_date = date_match.group(1)

            # Check which ticker this line is about
            for ticker in missing_tickers:
                # Use word boundary matching to avoid "S" matching "SHOP"
                if re.search(r'\b' + re.escape(ticker.upper()) + r'\b', line.upper()) and ticker.upper() not in found_set:
                    all_found.append({
                        "symbol": ticker,
                        "date": report_date,
                        "epsActual": None,
                        "epsEstimated": None,
                        "revenueActual": None,
                        "revenueEstimated": None,
                    })
                    found_set.add(ticker.upper())
                    print(f"  Perplexity fallback found: {ticker} reporting on {report_date}")

        return all_found

    except Exception as e:
        print(f"  Error in Perplexity weekly earnings check: {e}")
        return []


def fetch_week_earnings(start_date: str, end_date: str) -> list:
    """
    Fetch earnings calendar for a date range (week).
    """
    url = f"{FMP_STABLE_URL}/earnings-calendar"
    params = {
        "from": start_date,
        "to": end_date,
        "apikey": FMP_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching earnings calendar: {e}")
        return []


def create_weekly_preview_embed(upcoming_earnings: list) -> dict:
    """Create an embed showing upcoming earnings for the week."""

    # Group by date
    by_date = {}
    for earning in upcoming_earnings:
        date = earning.get("date", "Unknown")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(earning.get("symbol", "???"))

    # Build fields for each day
    fields = []
    for date in sorted(by_date.keys()):
        tickers = by_date[date]
        # Format date nicely
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            day_name = dt.strftime("%A, %b %d")
        except ValueError:
            day_name = date

        fields.append({
            "name": f"📅 {day_name}",
            "value": ", ".join(tickers),
            "inline": False
        })

    # Pluralize correctly
    count = len(upcoming_earnings)
    stock_word = "Stock" if count == 1 else "Stocks"

    return {
        "title": "📊 Upcoming Earnings This Week",
        "description": f"**{count}** CGM Recommended {stock_word} report earnings this week",
        "color": 0x5865F2,  # Discord blurple
        "fields": fields,
        "footer": {
            "text": "EarningsBot • Weekly Preview"
        }
    }


def process_weekly_preview() -> list:
    """
    Process upcoming earnings for the current week.
    Returns list of embeds to post.
    """
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    # Get Monday of current week
    monday = now - timedelta(days=now.weekday())
    friday = monday + timedelta(days=4)

    start_date = monday.strftime("%Y-%m-%d")
    end_date = friday.strftime("%Y-%m-%d")

    print(f"Fetching earnings for week: {start_date} to {end_date}...")

    # Fetch all earnings for the week from FMP
    calendar = fetch_week_earnings(start_date, end_date)
    print(f"Found {len(calendar)} total earnings reports this week from FMP")

    # Filter to watched tickers
    watched_earnings = filter_watched_earnings(calendar)
    print(f"Found {len(watched_earnings)} watched companies from FMP")

    # Use Perplexity fallback to catch tickers FMP missed
    print("Checking Perplexity for any missed weekly earnings...")
    missed_earnings = fetch_missing_weekly_earnings_perplexity(start_date, end_date, watched_earnings)
    if missed_earnings:
        print(f"Found {len(missed_earnings)} additional companies via Perplexity fallback")
        watched_earnings.extend(missed_earnings)
    else:
        print("No additional earnings found via Perplexity")

    if not watched_earnings:
        return []

    # Create preview embed
    return [create_weekly_preview_embed(watched_earnings)]


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


def save_buy_prices(buy_price_data: dict, filepath: str = "buy_prices.json"):
    """
    Save buy prices to JSON file, merging with existing data.
    Only updates tickers that have new buy prices.
    """
    existing = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = {}

    existing.update(buy_price_data)

    with open(filepath, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"Saved buy prices for {len(buy_price_data)} ticker(s) to {filepath}")


def process_earnings(date: str) -> tuple[list, int, int, dict]:
    """
    Process earnings for a given date.
    Returns (embeds, beats, misses, buy_price_data).
    """
    print(f"Fetching earnings for {date}...")

    # Get earnings calendar from FMP
    calendar = fetch_earnings_calendar(date)
    print(f"Found {len(calendar)} total earnings reports from FMP")

    # Filter to watched tickers
    watched_earnings = filter_watched_earnings(calendar)
    print(f"Found {len(watched_earnings)} watched companies from FMP")

    # Use Perplexity fallback to catch tickers FMP missed (free plan has incomplete data)
    print("Checking Perplexity for any missed earnings...")
    missed_earnings = fetch_missing_earnings_perplexity(date, watched_earnings)
    if missed_earnings:
        print(f"Found {len(missed_earnings)} additional companies via Perplexity fallback")
        watched_earnings.extend(missed_earnings)
    else:
        print("No additional earnings found via Perplexity")

    if not watched_earnings:
        return [], 0, 0, {}  # Return empty - don't post if no watched companies reported

    embeds = []
    total_beats = 0
    total_misses = 0
    buy_price_data = {}

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

        # Get stock quote for price movement
        print(f"  Fetching stock quote for {ticker}...")
        quote = fetch_stock_quote(ticker)
        stock_change_percent = None
        if quote:
            stock_change_percent = quote.get("changesPercentage")

        # Get guidance, takeaways, ATH status, and buy price using Perplexity AI
        guidance = None
        takeaways = None
        is_ath = False
        buy_price = None
        if PERPLEXITY_API_KEY and year and quarter:
            print(f"  Fetching guidance for {ticker}...")
            guidance = fetch_earnings_guidance(ticker, year, quarter)
            print(f"  Fetching takeaways for {ticker}...")
            takeaways = fetch_key_takeaways(ticker, year, quarter)
            print(f"  Checking ATH for {ticker}...")
            is_ath = check_all_time_high(ticker, announcement_date)
            print(f"  Fetching recommended buy price for {ticker}...")
            current_price = quote.get("price") if quote else None
            buy_price = fetch_recommended_buy_price(ticker, year, quarter, current_price)

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
            takeaways=takeaways,
            is_ath=is_ath,
            stock_change_percent=stock_change_percent,
            buy_price=buy_price
        )
        embeds.append(embed)

        # Track buy price for saving
        if buy_price:
            buy_price_data[ticker] = {
                "buy_price": buy_price,
                "date": date,
                "fiscal_period": fiscal_period
            }

    # Add summary embed at the beginning
    if len(embeds) > 1:
        summary = create_summary_embed(len(embeds), total_beats, total_misses)
        embeds.insert(0, summary)

    return embeds, total_beats, total_misses, buy_price_data


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
            guidance="Q1 2026 revenue expected between $118B-$122B",
            stock_change_percent=4.2,
            buy_price="$220.00"
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
            guidance=None,
            stock_change_percent=2.8,
            buy_price="$430.00"
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
            guidance="Q1 2026 subscriber growth to slow",
            stock_change_percent=-7.4,
            buy_price="$880.00"
        ),
    ]

    if post_to_discord(test_embeds):
        print("✅ Test embeds posted successfully!")
    else:
        print("❌ Failed to post test embeds")


def main():
    parser = argparse.ArgumentParser(description="EarningsBot - Discord earnings notifications")
    parser.add_argument("--date", help="Specific date to check (YYYY-MM-DD)", default=None)
    parser.add_argument("--weekly", action="store_true", help="Post weekly preview of upcoming earnings")
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

    # Run weekly preview mode
    if args.weekly:
        print("Running weekly preview...")
        embeds = process_weekly_preview()

        if not embeds:
            print("✅ No watched companies reporting this week - nothing to post")
            return

        if args.dry_run:
            print(f"\n[DRY RUN] Would post weekly preview")
            return

        if post_to_discord(embeds):
            print("✅ Posted weekly preview to Discord")
        else:
            print("❌ Failed to post weekly preview")
            sys.exit(1)
        return

    # Determine date to check
    check_date = args.date or get_yesterday_date()
    print(f"Checking earnings for: {check_date}")

    # Process earnings
    embeds, beats, misses, buy_price_data = process_earnings(check_date)

    # Save buy prices (even on dry run, so they can be tested)
    if buy_price_data:
        save_buy_prices(buy_price_data)

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
