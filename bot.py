#!/usr/bin/env python3
"""
bot.py - Main entry point for the Trade Journal Bot

WHAT THIS FILE DOES:
1. Loads configuration
2. Initializes the database
3. Sets up the Telegram bot with handlers
4. Starts polling for messages

This is the file you run to start the bot: python bot.py

LEARNING MOMENT: Entry Points
Every program needs a starting point. In Python, this is typically a file
that you run directly (python bot.py). The `if __name__ == "__main__":`
block at the bottom ensures code only runs when you execute this file
directly, not when it's imported by another file.

LEARNING MOMENT: Async/Await
Telegram bots use "async" code because they need to wait for network
responses. Instead of blocking (freezing) while waiting, async code can
handle other messages. The `async def` functions use `await` to pause
without blocking.
"""

import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

# Import our modules
from config import TELEGRAM_BOT_TOKEN, ALLOWED_USER_ID
from database.connection import init_database
from handlers.message_handler import (
    handle_message,
    handle_balance_command,
    handle_positions_command,
    handle_log_command,
    handle_status_command,
    handle_start_command,
    handle_help_command,
)


# Set up logging
# This helps you see what's happening when things go wrong
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def create_user_filter():
    """
    Create a filter to restrict bot access to specific users.

    If ALLOWED_USER_ID is set, only that user can use the bot.
    Otherwise, anyone can use it.
    """
    if ALLOWED_USER_ID:
        return filters.User(user_id=ALLOWED_USER_ID)
    return filters.ALL


async def error_handler(update: Update, context) -> None:
    """Log errors and notify user."""
    logger.error(f"Exception while handling an update: {context.error}")

    # Try to notify the user
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Sorry, something went wrong processing that message. "
            "Please check the format and try again."
        )


async def set_bot_commands(application) -> None:
    """
    Register bot commands with Telegram so they show in the dropdown menu.

    LEARNING MOMENT: Telegram Command Menu
    The "/" command dropdown in Telegram is NOT automatic from your code.
    You must explicitly register commands with Telegram via:
    1. BotFather's /setcommands, OR
    2. The set_my_commands API call (what we do here)

    This runs once when the bot starts.
    """
    from telegram import BotCommand

    commands = [
        BotCommand("status", "Check if bot is running"),
        BotCommand("positions", "Show open positions"),
        BotCommand("log", "Show trade history"),
        BotCommand("help", "Show examples"),
        BotCommand("start", "Welcome message"),
    ]

    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered with Telegram")


def main() -> None:
    """
    Main function - sets up and runs the bot.

    This is the "wiring" that connects all our modules together.
    """
    # Step 1: Initialize the database (creates tables if they don't exist)
    logger.info("Initializing database...")
    init_database()

    # Step 2: Create the Telegram application
    logger.info("Creating Telegram bot...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Step 2.5: Register commands with Telegram (for the dropdown menu)
    application.post_init = set_bot_commands

    # Step 3: Create user filter (for private bot access)
    user_filter = create_user_filter()

    # Step 4: Register command handlers
    # These respond to /command messages
    application.add_handler(
        CommandHandler("start", handle_start_command, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("help", handle_help_command, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("status", handle_status_command, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("positions", handle_positions_command, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("log", handle_log_command, filters=user_filter)
    )
    # Keep /balance as alias for /positions
    application.add_handler(
        CommandHandler("balance", handle_balance_command, filters=user_filter)
    )

    # Step 5: Register message handler
    # This handles all other text messages (the trade logging)
    # We filter for text messages only, and apply user filter
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & user_filter,
            handle_message
        )
    )

    # Step 6: Register error handler
    application.add_error_handler(error_handler)

    # Step 7: Start the bot!
    logger.info("Starting bot... Press Ctrl+C to stop.")
    if ALLOWED_USER_ID:
        logger.info(f"Bot restricted to user ID: {ALLOWED_USER_ID}")
    else:
        logger.info("Bot is open to all users")

    # Run the bot until Ctrl+C is pressed
    # This uses "polling" - the bot repeatedly asks Telegram for new messages
    application.run_polling(allowed_updates=Update.ALL_TYPES)


# This block runs only when you execute: python bot.py
# It does NOT run if you import this file from another file
if __name__ == "__main__":
    main()
