# Trade Journal Telegram Bot

A personal Telegram bot that turns your trade messages into a structured journal. Send a message about a trade, and the bot automatically logs it with price data from DEX Screener.

## What It Does

Send a message like:
```
0x20DD04c17AFD5c9a8b3f2cdacaa8Ee7907385BEF
Bought 1.5K USDC at $1.6M MCAP
```

The bot will:
1. Parse the contract address and amount
2. Look up the current token price from DEX Screener
3. Calculate how many tokens you bought
4. Save everything to a local database
5. Reply with a confirmation and position summary

## Quick Start

### 1. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow prompts to name your bot
4. Copy the token you receive (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Set Up the Project

```bash
# Navigate to the project folder
cd "trade journal bot"

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### 3. Configure

Edit `.env` and add your bot token:
```
TELEGRAM_BOT_TOKEN=your_token_here
```

Optionally, restrict to only your Telegram user ID:
```
ALLOWED_USER_ID=123456789
```
(Find your ID by messaging @userinfobot on Telegram)

### 4. Run the Bot

```bash
python bot.py
```

You should see:
```
Initializing database...
Database initialized at: trades.db
Creating Telegram bot...
Starting bot... Press Ctrl+C to stop.
```

Now message your bot on Telegram!

## Message Format Examples

### Buying
```
0x6982508145454Ce325dDbE47a25d4ec3d2311933
Bought $500 worth of PEPE at $1.2B MCAP
```

```
Aped 1.5K USDC into this https://dexscreener.com/solana/7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr
```

```
Entry on WIF - 100 SOL
7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr
```

### Selling
```
Sold PEPE for $2000
```

```
Exit 0x6982508145454Ce325dDbE47a25d4ec3d2311933
Got $1500 back
```

## Commands

- `/start` - Welcome message
- `/help` - Show help
- `/balance` - Show all open positions

## Supported Chains

- Ethereum
- Solana
- Base
- BNB Chain (BSC)
- Arbitrum
- Polygon
- And 80+ more via DEX Screener

## Project Structure

```
trade-journal-bot/
├── bot.py                 # Entry point - run this
├── config.py              # Settings loader
├── database/
│   ├── schema.sql         # Table definitions
│   ├── connection.py      # DB connection
│   └── models.py          # Read/write operations
├── parsing/
│   ├── patterns.py        # Regex patterns
│   ├── chain_detector.py  # Detect blockchain
│   └── message_parser.py  # Extract trade data
├── services/
│   ├── dex_screener.py    # Price lookups
│   └── position_tracker.py # PnL calculation
└── handlers/
    └── message_handler.py # Telegram handlers
```

## Database

All data is stored in `trades.db` (SQLite file). You can:
- Back it up by copying the file
- Query it directly with any SQLite tool
- Export for year-end tax review

## Troubleshooting

### "No contract address found"
Make sure to include the full contract address (0x... for EVM, or base58 for Solana) or a DEX Screener link.

### "Token not found on DEX Screener"
The token might be too new or have no liquidity. The trade will still be logged without price data.

### Bot not responding
1. Check Terminal for errors
2. Verify your bot token is correct in `.env`
3. Make sure `python bot.py` is running

## Running in Background (Optional)

To keep the bot running when you close Terminal:

```bash
# Using nohup
nohup python bot.py > bot.log 2>&1 &

# View logs
tail -f bot.log

# Stop the bot
pkill -f "python bot.py"
```

Or use a process manager like `pm2` or set up a LaunchAgent on macOS.
