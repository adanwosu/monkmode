# 🧘 Monk Mode - BTC/ETH Pair Trading Bot

A real-time trading signal bot that monitors BTC/ETH spread and sends alerts to Telegram and Discord when trading opportunities arise.

## Strategy Overview

**Monk's Pair Trading Strategy** exploits the relative strength divergence between BTC and ETH:

### Strategy 1: Long BTC / Short ETH
- **Trigger:** When market pumps and ETH outperforms BTC by ≥2%
- **Logic:** ETH tends to mean-revert after outperforming
- **Exit:** Close when spread normalizes and position is profitable

### Strategy 2: Short BTC / Long ETH
- **Trigger:** When market dumps and ETH underperforms BTC by ≥2%
- **Logic:** ETH tends to recover relative strength after underperforming
- **Exit:** Close when spread normalizes and position is profitable

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     MONK MODE BOT                           │
├─────────────────────────────────────────────────────────────┤
│  Signal Detection (Binance WebSocket)                       │
│  ├─ Real-time BTC/ETH prices                               │
│  ├─ 24h % change tracking                                  │
│  └─ Spread calculation                                      │
├─────────────────────────────────────────────────────────────┤
│  Platform Enrichment (REST APIs)                            │
│  ├─ Variational: mark price, bid/ask, funding rate         │
│  └─ Extended: mark price, bid/ask, funding rate            │
├─────────────────────────────────────────────────────────────┤
│  Notifications                                              │
│  ├─ Telegram Bot                                           │
│  └─ Discord Webhook                                        │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Clone and Install

```bash
cd monkmode
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Credentials

Copy `env.example` to `.env` and fill in your credentials:

```bash
cp env.example .env
```

#### Get Telegram Credentials:
1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
2. Message [@userinfobot](https://t.me/userinfobot) → copy your Chat ID

#### Get Discord Webhook:
1. Go to your Discord server → Settings → Integrations → Webhooks
2. Create New Webhook → Copy Webhook URL

### 3. Run Locally

```bash
python -m src.main
```

## Deploy to Railway

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/monkmode.git
git push -u origin main
```

### 2. Deploy on Railway

1. Go to [railway.app](https://railway.app)
2. New Project → Deploy from GitHub Repo
3. Select your `monkmode` repository
4. Go to Variables tab and add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `DISCORD_WEBHOOK_URL`
5. Railway will auto-deploy!

### 3. Verify

Check the Deployments tab for logs. You should see:
```
🧘 Starting Monk Mode Pair Trader
Telegram bot connected
Discord webhook connected
Starting Binance WebSocket stream...
```

## Configuration

Edit `config.yaml` to tune the strategy:

```yaml
strategy:
  spread_threshold: 2.0      # Min spread % to trigger signal
  spread_max: 8.0            # Max spread (filter anomalies)
  spread_close_threshold: 1.0 # Spread level to consider "normalized"
  position_size_usd: 1000    # Notional size per leg
  take_profit_usd: 25        # Min profit to suggest close
  cooldown_sec: 300          # Time between same-direction signals

notifications:
  telegram:
    enabled: true
  discord:
    enabled: true
  include_platforms:
    - variational
    - extended
```

## Alert Examples

### Entry Signal (Telegram)
```
🧘 MONK MODE ALERT

━━━━━━━━━━━━━━━━━━━━━
📈 STRATEGY 1 SIGNAL
━━━━━━━━━━━━━━━━━━━━━

Action: Long BTC / Short ETH
Reason: ETH outperforming BTC by 2.53%

📊 Binance (Signal Source)
├─ BTC: $97,432.50 (+2.34%)
├─ ETH: $3,842.18 (+4.87%)
└─ Spread: +2.53%

💹 VARIATIONAL
├─ BTC: $97,428.12 (FR: 0.0124%)
└─ ETH: $3,841.55 (FR: 0.0089%)

⏰ 2026-01-11 14:32:45 UTC

NFA. DYOR 🙏
```

### Close Signal (Telegram)
```
🧘 MONK MODE ALERT

━━━━━━━━━━━━━━━━━━━━━
💰 CLOSE POSITION SIGNAL
━━━━━━━━━━━━━━━━━━━━━

Action: Close All Positions
Reason: Spread normalized to +0.82%

📊 Position Summary
├─ Entry Spread: +2.53%
├─ Current Spread: +0.82%
├─ Duration: 2h 13m
└─ Est. PnL: 🟢 +$127.45

⏰ 2026-01-11 16:45:22 UTC

NFA. DYOR 🙏
```

## Project Structure

```
monkmode/
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── config.py            # Configuration loader
│   ├── api/
│   │   ├── __init__.py
│   │   ├── base.py          # Data models
│   │   ├── binance.py       # Binance WebSocket client
│   │   ├── variational.py   # Variational REST client
│   │   └── extended.py      # Extended REST client
│   ├── strategy/
│   │   ├── __init__.py
│   │   └── pair_trader.py   # Core strategy logic
│   └── notifiers/
│       ├── __init__.py
│       ├── base.py          # Alert formatting
│       ├── telegram.py      # Telegram notifier
│       └── discord.py       # Discord notifier
├── config.yaml              # Strategy settings
├── requirements.txt         # Python dependencies
├── Procfile                 # Railway process type
├── runtime.txt              # Python version
├── railway.toml             # Railway config
├── env.example              # Environment template
└── README.md
```

## Important Notes

⚠️ **NFA (Not Financial Advice)**
- This bot provides signals only, not automated trading
- Always verify signals before trading
- Start with small sizes to understand the strategy
- Beware of high-fee DEXs - this works best on low/zero fee platforms

## Troubleshooting

### Bot not receiving signals
- Check Binance WebSocket connection in logs
- Verify spread is actually crossing threshold
- Check cooldown hasn't been triggered

### Telegram not working
- Verify bot token is correct
- Make sure you've started a chat with your bot
- Check chat ID is your personal ID (not group ID unless intended)

### Discord not working
- Verify webhook URL is complete
- Check webhook hasn't been deleted
- Ensure bot has permission to post in channel

## License

MIT - Use at your own risk! 🧘

---

Built with ❤️ for the Monk Mode community
