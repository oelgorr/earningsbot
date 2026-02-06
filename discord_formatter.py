"""
Discord embed formatter for earnings reports.
Creates rich, visual embeds for Discord webhooks.
"""

from typing import Optional


def format_beat_miss(actual: float, estimate: float) -> str:
    """Return emoji indicator for beat/miss."""
    if actual is None or estimate is None:
        return "➖"
    if actual > estimate:
        return "✅"  # Beat
    elif actual < estimate:
        return "❌"  # Miss
    return "➖"  # Met


def format_number(value: float, prefix: str = "$", suffix: str = "") -> str:
    """Format large numbers with B/M suffixes."""
    if value is None:
        return "N/A"

    abs_value = abs(value)
    sign = "-" if value < 0 else ""

    if abs_value >= 1_000_000_000:
        return f"{sign}{prefix}{abs_value / 1_000_000_000:.2f}B{suffix}"
    elif abs_value >= 1_000_000:
        return f"{sign}{prefix}{abs_value / 1_000_000:.2f}M{suffix}"
    elif abs_value >= 1_000:
        return f"{sign}{prefix}{abs_value / 1_000:.2f}K{suffix}"
    else:
        return f"{sign}{prefix}{value:.2f}{suffix}"


def format_percent_change(current: float, previous: float) -> str:
    """Calculate and format YoY percent change."""
    if current is None or previous is None or previous == 0:
        return ""

    change = ((current - previous) / abs(previous)) * 100
    arrow = "📈" if change > 0 else "📉" if change < 0 else "➡️"
    return f" {arrow} {change:+.1f}% YoY"


def format_stock_movement(change_percent: Optional[float], is_premarket: bool = True) -> str:
    """Format stock price movement with emoji indicator."""
    if change_percent is None:
        return ""

    market_type = "pre-market" if is_premarket else "after-hours"

    if change_percent > 0:
        return f"📈 Stock is **up {change_percent:.1f}%** {market_type}"
    elif change_percent < 0:
        return f"📉 Stock is **down {abs(change_percent):.1f}%** {market_type}"
    else:
        return f"➡️ Stock is **flat** {market_type}"


def create_earnings_embed(
    ticker: str,
    company_name: str,
    fiscal_period: str,
    revenue_actual: Optional[float],
    revenue_estimate: Optional[float],
    revenue_previous: Optional[float],
    eps_actual: Optional[float],
    eps_estimate: Optional[float],
    eps_previous: Optional[float],
    guidance: Optional[str] = None,
    takeaways: Optional[list] = None,
    is_ath: bool = False,
    stock_change_percent: Optional[float] = None,
) -> dict:
    """
    Create a Discord embed for an earnings report.

    Returns a dict ready to be sent via Discord webhook.
    """

    # Determine overall sentiment for embed color
    beats = 0
    misses = 0

    if revenue_actual and revenue_estimate:
        if revenue_actual > revenue_estimate:
            beats += 1
        elif revenue_actual < revenue_estimate:
            misses += 1

    if eps_actual and eps_estimate:
        if eps_actual > eps_estimate:
            beats += 1
        elif eps_actual < eps_estimate:
            misses += 1

    # Green if mostly beats, red if mostly misses, gray if mixed/neutral
    if beats > misses:
        color = 0x00FF00  # Green
    elif misses > beats:
        color = 0xFF0000  # Red
    else:
        color = 0x808080  # Gray

    # Build the embed fields
    fields = []

    # Revenue field
    if revenue_actual is not None:
        rev_indicator = format_beat_miss(revenue_actual, revenue_estimate)
        rev_est_str = f" (Est: {format_number(revenue_estimate)})" if revenue_estimate else ""
        rev_yoy = format_percent_change(revenue_actual, revenue_previous)
        fields.append({
            "name": "💰 Revenue",
            "value": f"{format_number(revenue_actual)}{rev_est_str} {rev_indicator}{rev_yoy}",
            "inline": True
        })

    # EPS field
    if eps_actual is not None:
        eps_indicator = format_beat_miss(eps_actual, eps_estimate)
        eps_est_str = f" (Est: ${eps_estimate:.2f})" if eps_estimate else ""
        eps_yoy = format_percent_change(eps_actual, eps_previous)
        fields.append({
            "name": "📊 EPS",
            "value": f"${eps_actual:.2f}{eps_est_str} {eps_indicator}{eps_yoy}",
            "inline": True
        })

    # Guidance field (if available)
    if guidance:
        fields.append({
            "name": "🔮 Guidance",
            "value": guidance,
            "inline": False
        })

    # Key takeaways field (if available)
    if takeaways and len(takeaways) > 0:
        takeaways_text = "\n".join([f"• {t}" for t in takeaways])
        fields.append({
            "name": "📌 Key Takeaways",
            "value": takeaways_text,
            "inline": False
        })

    # Build title with optional ATH badge
    title = f"📈 {ticker} {fiscal_period} Earnings"
    if is_ath:
        title += " 🏆 ATH!"

    # Build description with company name, stock movement, and optional ATH note
    description = f"**{company_name}**"
    if stock_change_percent is not None:
        stock_movement = format_stock_movement(stock_change_percent)
        description += f"\n{stock_movement}"
    if is_ath:
        description += "\n🚀 *Stock reached all-time high!*"

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {
            "text": "EarningsBot • Data from Financial Modeling Prep"
        }
    }

    return embed


def create_summary_embed(total_reports: int, beats: int, misses: int) -> dict:
    """Create a summary embed for the day's earnings."""

    return {
        "title": "📋 Daily Earnings Summary",
        "description": f"**{total_reports}** companies in your watchlist reported earnings",
        "color": 0x5865F2,  # Discord blurple
        "fields": [
            {
                "name": "✅ Beats",
                "value": str(beats),
                "inline": True
            },
            {
                "name": "❌ Misses",
                "value": str(misses),
                "inline": True
            }
        ]
    }


def create_no_earnings_embed() -> dict:
    """Create an embed for when no watched companies reported."""

    return {
        "title": "📋 Daily Earnings Update",
        "description": "No companies in your watchlist reported earnings yesterday.",
        "color": 0x808080  # Gray
    }
