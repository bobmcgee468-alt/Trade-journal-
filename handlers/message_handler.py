"""
message_handler.py - Handle incoming Telegram messages

WHAT THIS FILE DOES:
Orchestrates the flow when a message arrives:
1. Parse the message to extract trade info
2. Look up token price from DEX Screener
3. Save to database and update position
4. Reply with confirmation

LEARNING MOMENT: Separation of Concerns
This file doesn't parse messages (parsing/ does that).
This file doesn't talk to APIs (services/ does that).
This file doesn't touch the database directly (database/ does that).

It just coordinates between them. This makes each piece easier to test
and modify independently.
"""

from telegram import Update
from telegram.ext import ContextTypes

from parsing.message_parser import parse_message, format_parse_summary, ParseResult
from services.position_tracker import (
    process_trade,
    TradeResult,
    find_position_for_exit,
    get_portfolio_summary
)
from services.dex_screener import get_token_info, DexScreenerError
from database import models


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle an incoming text message.

    This is called by the Telegram bot for every text message received.

    Args:
        update: Telegram update object containing the message
        context: Bot context (not used much here)
    """
    # Get the message text
    text = update.message.text
    if not text:
        return

    # Send a loading indicator immediately so user knows bot is working
    # LEARNING MOMENT: User Experience
    # API calls can take 1-3 seconds. Without feedback, users think the bot is broken.
    # We send a "processing" message first, then edit it with the result.
    loading_msg = await update.message.reply_text("⏳ Processing...")

    try:
        # Parse the message
        result = parse_message(text)

        if not result.success:
            # Parsing failed - edit loading message with error
            await loading_msg.edit_text(
                f"❌ Couldn't parse that message:\n{result.error_message}\n\n"
                "Please include a contract address or DEX Screener link."
            )
            return

        # Process each trade in the message
        responses = []
        for parsed_trade in result.trades:
            trade_result = process_trade(parsed_trade)
            responses.append(format_trade_result(trade_result))

        # Edit loading message with the result
        reply = "\n\n".join(responses)
        await loading_msg.edit_text(reply)

    except Exception as e:
        # If anything goes wrong, show error instead of leaving "Processing..."
        await loading_msg.edit_text(f"❌ Error: {str(e)}")


async def handle_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /balance command - redirects to /positions."""
    await handle_positions_command(update, context)


async def handle_positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /positions command - show all open positions with live prices.

    LEARNING MOMENT: Unrealized vs Realized PnL
    - Realized PnL: Profit/loss from trades you've closed (money in your pocket)
    - Unrealized PnL: Paper profit/loss on positions you still hold

    To calculate unrealized PnL:
    1. Fetch the current market price for each token
    2. Calculate: current_value = tokens_held * current_price
    3. Calculate: unrealized_pnl = current_value - what_you_paid
    """
    loading_msg = await update.message.reply_text("⏳ Loading positions and fetching live prices...")

    try:
        positions = models.get_all_open_positions()

        if not positions:
            await loading_msg.edit_text("No open positions.")
            return

        lines = ["📊 Open Positions", "─" * 25]

        # Totals for spot tokens (where we can fetch prices)
        total_invested = 0
        total_current_value = 0
        total_unrealized_pnl = 0
        spot_positions_count = 0

        for pos in positions:
            symbol = pos.get('symbol', 'UNKNOWN')
            chain = pos.get('chain', '?')
            contract_address = pos.get('contract_address', '')
            remaining = pos.get('remaining_tokens', 0) or 0
            cost = pos.get('total_cost_usd', 0) or 0

            total_invested += cost

            # Format tokens held
            if remaining >= 1_000_000:
                remaining_str = f"{remaining/1_000_000:.1f}M"
            elif remaining >= 1_000:
                remaining_str = f"{remaining/1_000:.1f}K"
            else:
                remaining_str = f"{remaining:,.0f}"

            lines.append(f"• {symbol} ({chain})")
            lines.append(f"  {remaining_str} tokens | ${cost:,.0f} invested")

            # Check if this is a perp/CEX position (synthetic address)
            # LEARNING MOMENT: Identifying Perps vs Spot
            # Perps use synthetic addresses like "BTC_hyperliquid" or "ETH_binance"
            # Real on-chain tokens have hex addresses starting with 0x (or base58 for Solana)
            is_perp = '_' in contract_address and not contract_address.startswith('0x')

            if is_perp:
                lines.append("  ⚠️ Price unavailable (perp)")
            else:
                # Fetch live price from DEX Screener
                try:
                    token_info = get_token_info(contract_address, chain)

                    if token_info and token_info.price_usd:
                        current_value = remaining * token_info.price_usd
                        unrealized_pnl = current_value - cost

                        # Track totals for spot tokens
                        total_current_value += current_value
                        total_unrealized_pnl += unrealized_pnl
                        spot_positions_count += 1

                        # Format PnL with sign and percentage
                        if cost > 0:
                            pnl_pct = (unrealized_pnl / cost) * 100
                            pnl_sign = "+" if unrealized_pnl >= 0 else ""
                            pnl_emoji = "💰" if unrealized_pnl >= 0 else "📉"
                            lines.append(f"  {pnl_emoji} Now: ${current_value:,.0f} | {pnl_sign}${unrealized_pnl:,.0f} ({pnl_sign}{pnl_pct:.1f}%)")
                        else:
                            lines.append(f"  💰 Now: ${current_value:,.0f}")
                    else:
                        lines.append("  ⚠️ Price unavailable")

                except DexScreenerError:
                    lines.append("  ⚠️ Price fetch failed")

        lines.append("─" * 25)
        lines.append(f"Total invested: ${total_invested:,.0f}")

        # Show unrealized PnL summary for spot positions
        if spot_positions_count > 0:
            total_pnl_sign = "+" if total_unrealized_pnl >= 0 else ""
            if total_invested > 0:
                total_pnl_pct = (total_unrealized_pnl / total_invested) * 100
                pnl_emoji = "💰" if total_unrealized_pnl >= 0 else "📉"
                lines.append(f"{pnl_emoji} Current value: ${total_current_value:,.0f} (spot)")
                lines.append(f"📊 Unrealized PnL: {total_pnl_sign}${total_unrealized_pnl:,.0f} ({total_pnl_sign}{total_pnl_pct:.1f}%)")

        # Add realized PnL
        stats = models.get_trading_stats()
        if stats['realized_pnl_usd'] != 0:
            pnl = stats['realized_pnl_usd']
            pnl_emoji = "📈" if pnl > 0 else "📉"
            lines.append(f"{pnl_emoji} Realized PnL: ${pnl:,.2f}")

        await loading_msg.edit_text("\n".join(lines))

    except Exception as e:
        await loading_msg.edit_text(f"❌ Error: {str(e)}")


async def handle_log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /log command - show all trade entries.

    Shows the trade journal history, most recent first.
    """
    loading_msg = await update.message.reply_text("⏳ Loading trade log...")

    try:
        trades = models.get_all_trades(limit=20)  # Last 20 trades

        if not trades:
            await loading_msg.edit_text("No trades recorded yet.")
            return

        lines = ["📒 Trade Log (last 20)", "─" * 30]

        for trade in trades:
            symbol = trade.get('symbol', '???')
            trade_type = trade.get('trade_type', '?')
            chain = trade.get('chain', '?')
            amount = trade.get('amount_spent') or trade.get('total_value_usd') or 0
            currency = trade.get('spend_currency', 'USD')
            timestamp = trade.get('trade_timestamp', '')
            position_status = trade.get('position_status', '')

            # Format timestamp (just date)
            if timestamp:
                date_str = str(timestamp)[:10]  # YYYY-MM-DD
            else:
                date_str = "?"

            # Trade type emoji
            type_emoji = "🟢" if trade_type == 'BUY' else "🔴"

            # Position status indicator
            status_indicator = ""
            if position_status == 'CLOSED':
                status_indicator = " ✓"
            elif position_status == 'PARTIAL':
                status_indicator = " ◐"

            # Format amount
            if amount >= 1000:
                amount_str = f"${amount/1000:.1f}K"
            else:
                amount_str = f"${amount:.0f}"

            lines.append(f"{type_emoji} {date_str} | {symbol} ({chain}) | {amount_str}{status_indicator}")

        lines.append("─" * 30)
        lines.append("✓ = closed | ◐ = partial")

        await loading_msg.edit_text("\n".join(lines))

    except Exception as e:
        await loading_msg.edit_text(f"❌ Error: {str(e)}")


async def handle_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /status command - show bot health status.
    """
    loading_msg = await update.message.reply_text("⏳ Checking status...")

    try:
        from datetime import datetime
        from config import ANTHROPIC_API_KEY, ENVIRONMENT

        lines = ["🤖 Bot Status", "─" * 20]

        # Environment (local vs production)
        if ENVIRONMENT == "railway":
            lines.append("🚂 Running on: Railway")
        elif ENVIRONMENT == "digitalocean":
            lines.append("🌐 Running on: DigitalOcean")
        else:
            lines.append("💻 Running on: Local")

        # Bot is running (obviously, if this responds)
        lines.append("✅ Bot: Online")

        # Check database
        try:
            stats = models.get_trading_stats()
            lines.append(f"✅ Database: OK ({stats['total_trades']} trades)")
        except Exception as e:
            lines.append(f"❌ Database: Error - {e}")

        # Check Claude API
        if ANTHROPIC_API_KEY:
            lines.append("✅ Claude API: Configured")
        else:
            lines.append("⚠️ Claude API: Not configured")

        # Current time
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"🕐 Time: {now}")

        await loading_msg.edit_text("\n".join(lines))

    except Exception as e:
        await loading_msg.edit_text(f"❌ Error: {str(e)}")


async def handle_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - welcome message."""
    welcome = """Welcome to your Trade Journal Bot!

Send me a message about your trades and I'll log them for you.

Examples:
• $1.5K USDC on https://dexscreener.com/base/0x...
• 100K hype 3x hyperliquid
• 10K BTC Spot Binance

I'll automatically:
• Parse any format using AI
• Look up token prices
• Track your positions

Commands:
/positions - Show open positions
/log - Show trade history
/help - Show examples
"""
    await update.message.reply_text(welcome)


async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = """Trade Journal Bot Help

📝 Logging Trades:
Just send a natural message - the bot uses AI to parse it.

Examples:
• $1.5K USDC on https://dexscreener.com/base/0x...
• Bought 1K USDC of 0x4ed4E862... at 50M mcap
• 100K hype 3x hyperliquid
• Long ETH on HL $500
• 10K BTC Spot Binance
• Sold PEPE for $3000

Supported:
• DEX trades (with contract address or DEX Screener link)
• Perps on Hyperliquid, Binance, Bybit
• CEX spot trades

Commands:
/positions - Show open positions
/log - Show trade history
/help - Show this message
"""
    await update.message.reply_text(help_text)


def format_trade_result(result: TradeResult) -> str:
    """Format a trade result for display in Telegram."""
    lines = []

    # Status emoji
    if result.success:
        emoji = "+" if result.trade_type == 'BUY' else "-"
        lines.append(f"{emoji} {result.trade_type} {result.token_symbol or 'token'}")
    else:
        lines.append(f"Failed: {result.message}")
        return "\n".join(lines)

    # Amount spent
    if result.amount_spent and result.spend_currency:
        if result.spend_currency in ('USD', 'USDC', 'USDT'):
            lines.append(f"Spent: ${result.amount_spent:,.2f} {result.spend_currency}")
        else:
            lines.append(f"Spent: {result.amount_spent:,.4f} {result.spend_currency}")

    # Tokens acquired
    if result.amount_tokens:
        lines.append(f"Tokens: {result.amount_tokens:,.2f}")

    # Price at trade
    if result.price_usd:
        lines.append(f"Price: ${result.price_usd:.8f}")

    # Market cap
    if result.market_cap:
        if result.market_cap >= 1_000_000:
            mcap_str = f"${result.market_cap / 1_000_000:.1f}M"
        else:
            mcap_str = f"${result.market_cap / 1_000:,.0f}K"
        lines.append(f"MCAP: {mcap_str}")

    # Position summary
    if result.position_summary:
        lines.append("")
        lines.append(result.position_summary)

    # Any warnings
    if result.message and "Warning" in result.message:
        lines.append("")
        lines.append(result.message)

    return "\n".join(lines)
