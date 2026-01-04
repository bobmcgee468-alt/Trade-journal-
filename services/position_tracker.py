"""
position_tracker.py - Match trades to positions and calculate PnL

WHAT THIS FILE DOES:
This is the "business logic" of the trade journal. When you buy or sell:
1. Finds or creates the right position
2. Updates the position's totals
3. Calculates realized PnL when you sell

LEARNING MOMENT: What is PnL?
PnL = Profit and Loss. There are two types:
- Realized PnL: Actual profit/loss from sales you've completed
- Unrealized PnL: Paper profit/loss on positions you still hold

Example:
1. Buy 1000 tokens for $100 (cost basis: $0.10 per token)
2. Sell 500 tokens for $200 (proceeds: $0.40 per token)
   Realized PnL = $200 - (500 * $0.10) = $200 - $50 = $150 profit
3. You still hold 500 tokens worth $200
   Unrealized PnL = $200 - $50 = $150 paper profit

LEARNING MOMENT: Cost Basis Methods
When you sell partial positions, which tokens did you sell?
- FIFO (First In First Out): Sell oldest tokens first
- LIFO (Last In First Out): Sell newest tokens first
- Average Cost: All tokens have the same average cost

We use Average Cost because it's simplest and good enough for a personal journal.
"""

from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import models
from services.dex_screener import get_token_info, get_pair_info, TokenInfo, DexScreenerError
from parsing.message_parser import ParsedTrade


@dataclass
class TradeResult:
    """Result of processing a trade."""
    success: bool
    trade_id: Optional[int] = None
    position_id: Optional[int] = None
    token_symbol: Optional[str] = None
    message: str = ""

    # For display
    trade_type: Optional[str] = None
    amount_spent: Optional[float] = None
    spend_currency: Optional[str] = None
    amount_tokens: Optional[float] = None
    price_usd: Optional[float] = None
    market_cap: Optional[float] = None
    position_summary: Optional[str] = None


def process_trade(parsed: ParsedTrade) -> TradeResult:
    """
    Process a parsed trade: save to database and update position.

    This is the main entry point called by the message handler.

    Args:
        parsed: ParsedTrade from the message parser

    Returns:
        TradeResult with success/failure info

    LEARNING MOMENT: Different Trade Types
    1. Spot trades with contract address: Look up on DEX Screener
    2. Perp trades: No contract address, use symbol + exchange as identifier
    3. CEX spot trades: No contract address, use symbol + exchange
    """
    result = TradeResult(success=False)
    import logging

    if not parsed.trade_type:
        parsed.trade_type = 'BUY'  # Default to buy

    result.trade_type = parsed.trade_type

    # Handle perp trades (no contract address needed)
    if parsed.is_perp or (parsed.exchange and not parsed.contract_address):
        return process_perp_or_cex_trade(parsed, result)

    # Validate we have minimum required info for spot trades
    if not parsed.contract_address:
        result.message = "No contract address found"
        return result

    # Step 1: Look up token info from DEX Screener
    token_info = None
    try:
        logging.info(f"Looking up token: {parsed.contract_address} on chain: {parsed.chain}")

        # First try as token address
        token_info = get_token_info(parsed.contract_address, parsed.chain)

        # If not found, try as pair address (DEX Screener URLs use pair addresses)
        if not token_info and parsed.chain:
            logging.info(f"Token not found, trying as pair address...")
            token_info = get_pair_info(parsed.contract_address, parsed.chain)

        if token_info:
            logging.info(f"Found token: {token_info.symbol} @ ${token_info.price_usd}")
        else:
            logging.warning(f"Token not found on DEX Screener")
    except Exception as e:
        # Continue without price - we'll save what we can
        logging.error(f"DEX Screener lookup failed: {type(e).__name__}: {e}")
        result.message = f"Warning: Could not fetch price - {e}"

    # Step 2: Get or create token in database
    chain = parsed.chain
    symbol = parsed.token_symbol
    name = None

    if token_info:
        chain = token_info.chain
        symbol = token_info.symbol
        name = token_info.name
        result.price_usd = token_info.price_usd
        result.market_cap = token_info.market_cap

    if not chain:
        chain = 'unknown'

    token_id = models.get_or_create_token(
        contract_address=parsed.contract_address,
        chain=chain,
        symbol=symbol,
        name=name
    )

    result.token_symbol = symbol

    # Step 3: Find or create position
    position = models.get_open_position(token_id)

    if parsed.trade_type == 'BUY':
        if not position:
            position_id = models.create_position(token_id)
            position = models.get_position_by_id(position_id)
        else:
            position_id = position['id']
    else:  # SELL
        if not position:
            result.message = f"No open position found for {symbol or parsed.contract_address}. Recording trade anyway."
            position_id = models.create_position(token_id)
            position = models.get_position_by_id(position_id)
        else:
            position_id = position['id']

    result.position_id = position_id

    # Step 4: Calculate token amount if we have price
    amount_tokens = None
    total_value_usd = None

    if parsed.amount_spent and token_info and token_info.price_usd:
        # Calculate tokens from spend amount
        if parsed.spend_currency in ('USD', 'USDC', 'USDT', 'DAI'):
            amount_tokens = parsed.amount_spent / token_info.price_usd
            total_value_usd = parsed.amount_spent
        else:
            # For ETH, SOL, etc. we'd need to look up their prices
            # For now, just record what we know
            total_value_usd = None

    result.amount_spent = parsed.amount_spent
    result.spend_currency = parsed.spend_currency
    result.amount_tokens = amount_tokens

    # Step 5: Create trade record
    trade_id = models.create_trade(
        token_id=token_id,
        trade_type=parsed.trade_type,
        position_id=position_id,
        amount_spent=parsed.amount_spent,
        spend_currency=parsed.spend_currency,
        amount_tokens=amount_tokens,
        price_usd=token_info.price_usd if token_info else None,
        total_value_usd=total_value_usd,
        market_cap_at_trade=parsed.market_cap or (token_info.market_cap if token_info else None),
        source_message=parsed.raw_message,
        notes_url=parsed.notes_url,
        dex_screener_url=parsed.dex_screener_url or (token_info.dex_url if token_info else None)
    )

    result.trade_id = trade_id

    # Step 6: Update position
    if position and amount_tokens and total_value_usd:
        update_position_from_trade(
            position=position,
            trade_type=parsed.trade_type,
            amount_tokens=amount_tokens,
            total_value_usd=total_value_usd
        )

    # Step 7: Generate position summary
    updated_position = models.get_position_by_id(position_id)
    if updated_position:
        result.position_summary = format_position_summary(updated_position)

    result.success = True
    if not result.message:
        result.message = f"Trade recorded successfully"

    return result


def process_perp_or_cex_trade(parsed: ParsedTrade, result: TradeResult) -> TradeResult:
    """
    Process a perp or CEX spot trade (no contract address).

    For perps and CEX trades, we use symbol + exchange as the identifier
    instead of a contract address.

    LEARNING MOMENT: Why No Contract Address?
    - Perps: You're trading a derivative, not the actual token
    - CEX Spot: The exchange holds the tokens, you don't have on-chain position
    In both cases, we track by symbol (e.g., "BTC") + venue (e.g., "hyperliquid")
    """
    result.trade_type = parsed.trade_type

    # Create a synthetic "contract address" for database purposes
    # Format: symbol_exchange (e.g., "BTC_hyperliquid", "ETH_binance")
    symbol = parsed.token_symbol or 'UNKNOWN'
    exchange = parsed.exchange or 'unknown'
    synthetic_address = f"{symbol}_{exchange}"

    # For perps, chain is the exchange
    chain = exchange

    result.token_symbol = symbol
    result.amount_spent = parsed.amount_spent
    result.spend_currency = parsed.spend_currency

    # Get or create token in database
    token_id = models.get_or_create_token(
        contract_address=synthetic_address,
        chain=chain,
        symbol=symbol,
        name=f"{symbol} {'Perp' if parsed.is_perp else 'Spot'} on {exchange.title()}"
    )

    # Find or create position
    position = models.get_open_position(token_id)

    if parsed.trade_type == 'BUY':
        if not position:
            position_id = models.create_position(token_id)
            position = models.get_position_by_id(position_id)
        else:
            position_id = position['id']
    else:  # SELL
        if not position:
            result.message = f"No open position found for {symbol}. Recording trade anyway."
            position_id = models.create_position(token_id)
            position = models.get_position_by_id(position_id)
        else:
            position_id = position['id']

    result.position_id = position_id

    # For perps/CEX, we track in USD value (no token amount)
    amount_tokens = None
    total_value_usd = parsed.amount_spent if parsed.spend_currency in ('USD', 'USDC', 'USDT') else None

    # If amount is in USD, use it as both amount and value
    if total_value_usd:
        amount_tokens = total_value_usd  # Treat as "position size in USD"

    result.amount_tokens = amount_tokens

    # Create trade record
    trade_id = models.create_trade(
        token_id=token_id,
        trade_type=parsed.trade_type,
        position_id=position_id,
        amount_spent=parsed.amount_spent,
        spend_currency=parsed.spend_currency,
        amount_tokens=amount_tokens,
        price_usd=1.0,  # For USD-denominated perps, price is 1:1
        total_value_usd=total_value_usd,
        market_cap_at_trade=None,
        source_message=parsed.raw_message,
        notes_url=parsed.notes_url,
        dex_screener_url=None
    )

    result.trade_id = trade_id

    # Update position
    if position and amount_tokens and total_value_usd:
        update_position_from_trade(
            position=position,
            trade_type=parsed.trade_type,
            amount_tokens=amount_tokens,
            total_value_usd=total_value_usd
        )

    # Generate position summary
    updated_position = models.get_position_by_id(position_id)
    if updated_position:
        result.position_summary = format_position_summary(updated_position)

    result.success = True
    venue_type = "perp" if parsed.is_perp else "spot"
    result.message = f"{symbol} {venue_type} on {exchange.title()} recorded"

    return result


def update_position_from_trade(
    position: Dict[str, Any],
    trade_type: str,
    amount_tokens: float,
    total_value_usd: float
) -> None:
    """
    Update a position's totals after a trade.

    LEARNING MOMENT: Average Cost Basis
    When you buy multiple times, your cost basis is the average:
    - Buy 100 tokens for $10 ($0.10 each)
    - Buy 100 tokens for $20 ($0.20 each)
    - Average cost = $30 / 200 = $0.15 each

    When you sell, we use this average to calculate profit.
    """
    position_id = position['id']
    current_bought = position['total_bought'] or 0
    current_sold = position['total_sold'] or 0
    current_remaining = position['remaining_tokens'] or 0
    current_cost = position['total_cost_usd'] or 0
    current_proceeds = position['total_proceeds_usd'] or 0
    current_pnl = position['realized_pnl_usd'] or 0

    if trade_type == 'BUY':
        new_bought = current_bought + amount_tokens
        new_remaining = current_remaining + amount_tokens
        new_cost = current_cost + total_value_usd

        models.update_position(
            position_id=position_id,
            total_bought=new_bought,
            remaining_tokens=new_remaining,
            total_cost_usd=new_cost,
            status='OPEN'
        )

    else:  # SELL
        new_sold = current_sold + amount_tokens
        new_remaining = current_remaining - amount_tokens
        new_proceeds = current_proceeds + total_value_usd

        # Calculate realized PnL using average cost basis
        if current_bought > 0:
            avg_cost_per_token = current_cost / current_bought
            cost_of_sold = amount_tokens * avg_cost_per_token
            realized_pnl = total_value_usd - cost_of_sold
            new_pnl = current_pnl + realized_pnl
        else:
            new_pnl = current_pnl

        # Determine new status
        if new_remaining <= 0:
            status = 'CLOSED'
            new_remaining = 0  # Prevent negative
        else:
            status = 'PARTIAL'

        models.update_position(
            position_id=position_id,
            total_sold=new_sold,
            remaining_tokens=new_remaining,
            total_proceeds_usd=new_proceeds,
            realized_pnl_usd=new_pnl,
            status=status
        )


def format_position_summary(position: Dict[str, Any]) -> str:
    """Format a position for display."""
    symbol = position.get('symbol', 'UNKNOWN')
    status = position.get('status', 'UNKNOWN')
    remaining = position.get('remaining_tokens', 0) or 0
    total_cost = position.get('total_cost_usd', 0) or 0
    total_bought = position.get('total_bought', 0) or 0
    realized_pnl = position.get('realized_pnl_usd', 0) or 0

    lines = [f"Position: {symbol} ({status})"]

    if remaining > 0 and total_bought > 0:
        avg_cost = total_cost / total_bought
        lines.append(f"Holding: {remaining:,.0f} tokens")
        lines.append(f"Avg cost: ${avg_cost:.6f}")

    if realized_pnl != 0:
        pnl_emoji = "+" if realized_pnl > 0 else ""
        lines.append(f"Realized PnL: {pnl_emoji}${realized_pnl:,.2f}")

    return "\n".join(lines)


def find_position_for_exit(symbol: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Find the right position when user exits by symbol name.

    Returns:
        (position, message) - position if found (or None), and a message
    """
    positions = models.get_open_positions_by_symbol(symbol)

    if not positions:
        return None, f"No open position found for {symbol}"

    if len(positions) == 1:
        return positions[0], ""

    # Multiple positions - ask user to clarify
    lines = [f"Multiple open positions for {symbol}:"]
    for i, pos in enumerate(positions, 1):
        addr = pos.get('contract_address', '')
        short_addr = f"{addr[:6]}...{addr[-4:]}" if addr else 'N/A'
        chain = pos.get('chain', 'unknown')
        remaining = pos.get('remaining_tokens', 0)
        lines.append(f"{i}. {short_addr} ({chain}) - {remaining:,.0f} tokens")

    lines.append("\nPlease specify which position by including the contract address.")

    return None, "\n".join(lines)


def get_portfolio_summary() -> str:
    """Generate a summary of all open positions."""
    positions = models.get_all_open_positions()

    if not positions:
        return "No open positions."

    lines = ["Open Positions:"]
    lines.append("-" * 30)

    total_cost = 0
    for pos in positions:
        symbol = pos.get('symbol', 'UNKNOWN')
        chain = pos.get('chain', '?')
        remaining = pos.get('remaining_tokens', 0) or 0
        cost = pos.get('total_cost_usd', 0) or 0

        total_cost += cost
        lines.append(f"{symbol} ({chain}): {remaining:,.0f} tokens, ${cost:,.2f} invested")

    lines.append("-" * 30)
    lines.append(f"Total invested: ${total_cost:,.2f}")

    stats = models.get_trading_stats()
    lines.append(f"Total realized PnL: ${stats['realized_pnl_usd']:,.2f}")

    return "\n".join(lines)
