"""
config.py - Load settings from environment variables

WHAT THIS FILE DOES:
This file loads your secret configuration (like your Telegram bot token) from a
.env file instead of hardcoding them in your code. This is important because:
1. You never want secrets in your code (they'd end up on GitHub)
2. Different environments (your Mac vs a server) need different settings
3. It's easy to change settings without editing code

HOW IT WORKS:
1. python-dotenv reads the .env file and puts values into environment variables
2. os.getenv() reads those environment variables
3. We provide defaults or raise errors for required values

LEARNING MOMENT: Environment Variables
Environment variables are key-value pairs available to all programs on your computer.
They're like global settings. The .env file is just a convenient way to set them
for this specific project without affecting your whole system.
"""

import os
from dotenv import load_dotenv

# Load .env file into environment variables
# This looks for a file named ".env" in the same directory as this script
load_dotenv()


def get_required_env(key: str) -> str:
    """
    Get an environment variable that MUST exist.
    Raises an error with a helpful message if it's missing.
    """
    value = os.getenv(key)
    if value is None:
        raise ValueError(
            f"Missing required environment variable: {key}\n"
            f"Please copy .env.example to .env and fill in your values."
        )
    return value


# Required settings
TELEGRAM_BOT_TOKEN = get_required_env("TELEGRAM_BOT_TOKEN")

# Optional settings (with defaults)
# If you set ALLOWED_USER_ID, only that user can use the bot
# Leave it unset (or empty) to allow anyone
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")
if ALLOWED_USER_ID:
    ALLOWED_USER_ID = int(ALLOWED_USER_ID)

# Database file location (relative to project root)
DATABASE_PATH = os.getenv("DATABASE_PATH", "trades.db")

# DEX Screener API (no auth needed, but we define the base URL here)
DEXSCREENER_API_BASE = "https://api.dexscreener.com"

# Anthropic API Key (for Claude-powered message parsing)
# Optional - if not set, falls back to regex parsing
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Environment indicator (set to "digitalocean" on the server)
# Used by /status command to show where the bot is running
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
