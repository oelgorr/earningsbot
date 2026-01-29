# EarningsBot Configuration
# Capital Gains Multiplier Watchlist (49 companies)

WATCHED_TICKERS = [
    # SaaS & Cloud
    "ASAN", "DOCN", "DOCS", "HUBS", "MNDY", "CRWD", "DDOG", "NET", "S",
    # E-commerce & Marketplaces
    "MELI", "SHOP", "SE", "CPNG", "GRAB", "FVRR", "ABNB", "AMZN",
    # Fintech & Payments
    "OTCM", "DLO", "STNE", "NU", "ADYEY", "FOUR", "LMND", "NDAQ",
    # Advertising & Media
    "PUBM", "TTD", "PERI", "ROKU", "META", "GOOG",
    # Consumer & Lifestyle
    "DUOL", "DCBO", "HIMS", "LULU", "DECK",
    # Global & Emerging
    "GLBE", "BOC", "HESAF", "ESLOY", "BYDDY",
    # Tech & Hardware
    "KNSL", "TSLA", "ASML", "MU", "ENPH",
    # Healthcare & Specialty
    "MEDP", "TMDX", "RACE",
]

# Discord Webhook URL (get from Server Settings → Integrations → Webhooks)
# Set this as an environment variable: DISCORD_WEBHOOK_URL
DISCORD_WEBHOOK_URL = None  # Will be loaded from environment

# Financial Modeling Prep API Key
# Sign up at: https://financialmodelingprep.com/developer
# Set this as an environment variable: FMP_API_KEY
FMP_API_KEY = None  # Will be loaded from environment

# Timezone for "yesterday's earnings" calculation
TIMEZONE = "America/New_York"

# Post timing (when the bot runs)
POST_HOUR = 7  # 7 AM Eastern
