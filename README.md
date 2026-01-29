# EarningsBot 📈

Automatically post earnings reports to your Discord server every morning. Tracks 60+ companies and posts revenue, EPS, and beat/miss indicators.

## What You'll Get

Every morning at 7 AM Eastern, your Discord will receive posts like:

> 📈 **AAPL Q4 2025 Earnings**
> **Apple Inc.**
>
> 💰 Revenue: $94.93B (Est: $94.50B) ✅ 📈 +6.1% YoY
> 📊 EPS: $1.64 (Est: $1.60) ✅ 📈 +12.3% YoY
> 🔮 Guidance: Q1 2026 revenue expected between $118B-$122B

## Quick Start (15 minutes)

### Step 1: Get Your API Keys

1. **Financial Modeling Prep** (earnings data)
   - Go to [financialmodelingprep.com/developer](https://financialmodelingprep.com/developer)
   - Sign up for the Starter plan (~$29/month)
   - Copy your API key from the dashboard

2. **Discord Webhook**
   - Open Discord → Your Server → Server Settings
   - Go to Integrations → Webhooks → New Webhook
   - Name it "EarningsBot", select your channel
   - Click "Copy Webhook URL"

### Step 2: Set Up GitHub Repository

1. Create a new GitHub repository (private is fine)
2. Upload all the files from this folder to the repository

### Step 3: Add Secrets to GitHub

1. In your GitHub repo, go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret** and add:
   - Name: `FMP_API_KEY` → Value: your Financial Modeling Prep API key
   - Name: `DISCORD_WEBHOOK_URL` → Value: your Discord webhook URL

### Step 4: Customize Your Watchlist

Edit `config.py` and replace the default tickers with your 60 companies:

```python
WATCHED_TICKERS = [
    "AAPL", "MSFT", "GOOGL",  # Add your tickers here
    # ...
]
```

### Step 5: Test It

1. Go to your GitHub repo → **Actions** tab
2. Click **Daily Earnings Report** → **Run workflow**
3. Check your Discord channel!

## Local Testing

If you want to test locally before deploying:

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in your credentials
cp .env.example .env
# Edit .env with your API keys

# Test with sample data (posts to Discord)
python earnings_bot.py --test

# Check yesterday's earnings without posting
python earnings_bot.py --dry-run

# Check a specific date
python earnings_bot.py --date 2025-01-28
```

## File Structure

```
EarningsBot/
├── earnings_bot.py      # Main script
├── discord_formatter.py # Creates Discord embeds
├── config.py            # Your watchlist + settings
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── .github/
│   └── workflows/
│       └── daily_earnings.yml  # GitHub Actions schedule
└── README.md
```

## Customization

### Change Posting Time

Edit `.github/workflows/daily_earnings.yml`:

```yaml
schedule:
  - cron: '0 12 * * *'  # 12:00 UTC = 7:00 AM Eastern
```

Use [crontab.guru](https://crontab.guru) to generate cron expressions.

### Skip Weekends

Most earnings are announced on weekdays. To skip weekends, modify the cron:

```yaml
schedule:
  - cron: '0 12 * * 1-5'  # Monday through Friday only
```

### Change Timezone

Edit `config.py`:

```python
TIMEZONE = "America/New_York"  # Change to your timezone
```

## Troubleshooting

### "No companies reported earnings"
This is normal! Not every day has earnings from your watchlist. The bot will post this message to confirm it's running.

### API Rate Limits
Financial Modeling Prep has rate limits. If you're tracking 60+ companies, the Starter plan should be sufficient. If you see rate limit errors, you may need to upgrade or reduce your watchlist.

### Workflow Not Running
- Check that GitHub Actions is enabled for your repository
- Verify your secrets are named exactly `FMP_API_KEY` and `DISCORD_WEBHOOK_URL`
- Check the Actions tab for error logs

## Cost

- **Financial Modeling Prep**: ~$29/month (Starter plan)
- **GitHub Actions**: Free (runs ~30 seconds/day)
- **Discord Webhook**: Free

---

Built with ❤️ for the investing community
