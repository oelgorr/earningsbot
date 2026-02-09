#!/usr/bin/env python3
"""
Woof of Wall Street - Interactive Discord bot for buy price lookups.

Users can @mention the bot to ask about buy prices for tracked stocks.

Usage:
    python interactive_bot.py

Commands (when @mentioning the bot):
    @Woof of Wall Street AMZN           - Get buy price for AMZN
    @Woof of Wall Street price AMZN     - Get buy price for AMZN
    @Woof of Wall Street list           - Show all tracked buy prices
    @Woof of Wall Street help           - Show available commands
"""

import os
import re
import json
from typing import Optional
import requests
import discord
from discord import Embed
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")
FMP_STABLE_URL = "https://financialmodelingprep.com/stable"

BUY_PRICES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "buy_prices.json")


def load_buy_prices(filepath: str = BUY_PRICES_FILE) -> dict:
    """Load buy prices from JSON file."""
    if not os.path.exists(filepath):
        return {}

    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def parse_price(price_str: str) -> Optional[float]:
    """Parse a dollar amount string like '$190.00' into a float."""
    match = re.search(r'\$?([\d,]+\.?\d*)', price_str)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def fetch_stock_quote(ticker: str) -> Optional[dict]:
    """Fetch real-time stock quote from FMP API."""
    if not FMP_API_KEY:
        return None

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
    except requests.RequestException:
        return None


def extract_ticker(message_text: str) -> Optional[str]:
    """
    Extract a stock ticker from the user's message.
    Handles various formats like:
        "AMZN", "price AMZN", "what's the buy price of AMZN?",
        "buy price for AMZN", "AMZN buy price"
    """
    # Remove bot mention and clean up
    text = re.sub(r'<@!?\d+>', '', message_text).strip()

    # Remove common words to isolate the ticker
    text = re.sub(r'\b(what|whats|what\'s|is|the|buy|price|of|for|current|get|show|check)\b', '', text, flags=re.IGNORECASE)
    text = text.strip('? .,!')

    # Look for an uppercase ticker-like word (1-5 uppercase letters)
    # Try the cleaned text first
    match = re.search(r'\b([A-Z]{1,5})\b', text.upper())
    if match:
        return match.group(1)

    return None


def create_buy_price_embed(ticker: str, buy_data: dict, current_price: Optional[float] = None) -> Embed:
    """Create a Discord embed showing the buy price for a ticker."""
    buy_price_str = buy_data.get("buy_price", "N/A")
    fiscal_period = buy_data.get("fiscal_period", "Unknown")
    date = buy_data.get("date", "Unknown")
    buy_price = parse_price(buy_price_str)

    # Determine color based on current price vs buy price
    if current_price and buy_price:
        if current_price <= buy_price:
            color = 0x00FF00  # Green - at or below buy price
            status = f"📈 **Below buy price!** ({((buy_price - current_price) / buy_price) * 100:.1f}% discount)"
        else:
            color = 0xFF9900  # Orange - above buy price
            status = f"⏳ **Above buy price** ({((current_price - buy_price) / buy_price) * 100:.1f}% above)"
    else:
        color = 0x5865F2  # Discord blurple
        status = ""

    embed = Embed(
        title=f"💲 {ticker} Buy Price",
        color=color
    )

    embed.add_field(name="🎯 Buy Below", value=buy_price_str, inline=True)

    if current_price:
        embed.add_field(name="💰 Current Price", value=f"${current_price:.2f}", inline=True)

    if status:
        embed.add_field(name="📊 Status", value=status, inline=False)

    embed.add_field(name="📅 Based On", value=f"{fiscal_period} Earnings ({date})", inline=False)
    embed.set_footer(text="Woof of Wall Street • Data from Financial Modeling Prep")

    return embed


def create_list_embed(buy_prices: dict) -> Embed:
    """Create an embed listing all tracked buy prices."""
    if not buy_prices:
        return Embed(
            title="🐕 Tracked Buy Prices",
            description="No buy prices tracked yet. Prices are set automatically after earnings reports.",
            color=0x808080
        )

    lines = []
    for ticker in sorted(buy_prices.keys()):
        data = buy_prices[ticker]
        price = data.get("buy_price", "N/A")
        period = data.get("fiscal_period", "")
        lines.append(f"**{ticker}** — {price} ({period})")

    embed = Embed(
        title="🐕 All Tracked Buy Prices",
        description="\n".join(lines),
        color=0x5865F2
    )
    embed.set_footer(text=f"Woof of Wall Street • {len(buy_prices)} stocks tracked")

    return embed


def create_help_embed() -> Embed:
    """Create a help embed showing available commands."""
    embed = Embed(
        title="🐕 Woof of Wall Street — Help",
        description="Mention me and ask about any tracked stock!",
        color=0x5865F2
    )

    embed.add_field(
        name="📈 Get Buy Price",
        value="`@Woof of Wall Street AMZN`\n`@Woof of Wall Street what's the buy price of AMZN?`",
        inline=False
    )
    embed.add_field(
        name="📋 List All Prices",
        value="`@Woof of Wall Street list`",
        inline=False
    )
    embed.add_field(
        name="❓ Help",
        value="`@Woof of Wall Street help`",
        inline=False
    )

    embed.set_footer(text="Woof of Wall Street • Buy prices are updated after each earnings report")

    return embed


def create_not_found_embed(ticker: str) -> Embed:
    """Create an embed for when a ticker isn't tracked."""
    return Embed(
        title=f"❓ {ticker} Not Found",
        description=f"**{ticker}** doesn't have a buy price set yet.\n\nBuy prices are automatically generated after a company reports earnings. Use `@Woof of Wall Street list` to see all tracked stocks.",
        color=0xFF0000
    )


# Set up Discord bot
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"✅ {client.user} is online and listening for messages!")
    print(f"   Bot ID: {client.user.id}")
    print(f"   Servers: {len(client.guilds)}")

    buy_prices = load_buy_prices()
    print(f"   Tracking {len(buy_prices)} stock(s) with buy prices")


@client.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # Only respond to @mentions
    if client.user not in message.mentions:
        return

    # Get the message text without the mention
    text = re.sub(r'<@!?\d+>', '', message.content).strip().lower()

    # Handle "help" command
    if text in ("help", "commands", "?"):
        await message.channel.send(embed=create_help_embed())
        return

    # Handle "list" command
    if text in ("list", "all", "prices", "show all"):
        buy_prices = load_buy_prices()
        await message.channel.send(embed=create_list_embed(buy_prices))
        return

    # Try to extract a ticker
    ticker = extract_ticker(message.content)

    if not ticker:
        await message.channel.send(embed=create_help_embed())
        return

    # Look up the ticker
    buy_prices = load_buy_prices()
    ticker = ticker.upper()

    if ticker not in buy_prices:
        await message.channel.send(embed=create_not_found_embed(ticker))
        return

    # Fetch current price
    quote = fetch_stock_quote(ticker)
    current_price = quote.get("price") if quote else None

    # Send the buy price embed
    embed = create_buy_price_embed(ticker, buy_prices[ticker], current_price)
    await message.channel.send(embed=embed)


def main():
    if not DISCORD_BOT_TOKEN:
        print("Error: DISCORD_BOT_TOKEN environment variable not set")
        print("Get your bot token from: https://discord.com/developers/applications")
        exit(1)

    if not FMP_API_KEY:
        print("Warning: FMP_API_KEY not set - current prices won't be available")

    print("Starting Woof of Wall Street...")
    client.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
