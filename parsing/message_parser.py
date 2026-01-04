"""
message_parser.py - Extract structured trade data from natural language messages

WHAT THIS FILE DOES:
Takes a raw Telegram message like:
    "0x20DD04c17AFD5c9a8b3f2cdacaa8Ee7907385BEF
    Bought 1.5K USDC worth of this at $1.6M MCAP
    Thesis https://members.delphidigital.io/feed/..."

And turns it into structured data:
    {
        'trade_type': 'BUY',
        'addresses': [ChainInfo(chain='ethereum', address='0x20DD...', ...)],
        'amount_spent': 1500.0,
        'spend_currency': 'USDC',
        'market_cap': 1600000.0,
        'notes_url': 'https://members.delphidigital.io/feed/...',
        ...
    }

LEARNING MOMENT: LLM vs Regex Parsing
We use Claude API as the primary parser because:
1. It handles any message format naturally
2. No need to maintain complex regex patterns
3. Cost is negligible (~$0.00025 per message with Haiku)

The regex code is kept as a fallback in case the API fails.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
import logging

# Try to import Claude parser
try:
    from services.claude_parser import parse_with_claude, ClaudeParsedTrade, ANTHROPIC_AVAILABLE
    from config import ANTHROPIC_API_KEY
    CLAUDE_AVAILABLE = ANTHROPIC_AVAILABLE and ANTHROPIC_API_KEY
except ImportError:
    CLAUDE_AVAILABLE = False

from .patterns import (
    extract_evm_addresses,
    extract_solana_addresses,
    extract_dexscreener_info,
    extract_usd_amounts,
    extract_crypto_amounts,
    extract_market_cap,
    detect_trade_type,
    extract_urls,
    extract_perp_info,
    detect_exchange,
    is_perp_trade,
    is_spot_trade,
    extract_cex_spot_info,
)
from .chain_detector import ChainInfo, create_chain_info, detect_chain_from_text


@dataclass
class ParsedTrade:
    """
    Structured data extracted from a trade message.
    All fields are Optional because we might not be able to extract everything.
    """
    # Core trade info
    trade_type: Optional[str] = None          # 'BUY' or 'SELL'
    contract_address: Optional[str] = None    # The token's contract address
    chain: Optional[str] = None               # Which blockchain
    token_symbol: Optional[str] = None        # If mentioned (e.g., "PEPE")

    # Amounts
    amount_spent: Optional[float] = None      # How much was spent
    spend_currency: Optional[str] = None      # Currency spent (USD, USDC, ETH, etc.)

    # Context
    market_cap: Optional[float] = None        # Market cap at time of trade
    notes_url: Optional[str] = None           # Thesis or notes link
    dex_screener_url: Optional[str] = None    # If a DEX Screener link was provided

    # Perps/Derivatives specific fields
    # LEARNING MOMENT: Spot vs Derivatives
    # Spot trades = buying/selling actual tokens (need contract address)
    # Derivatives = trading contracts that track price (just need symbol)
    is_perp: bool = False                     # Is this a perp/futures trade?
    exchange: Optional[str] = None            # Exchange (hyperliquid, binance, etc.)
    position_type: Optional[str] = None       # 'LONG' or 'SHORT' for perps

    # Metadata
    raw_message: str = ""                     # Original message for reference
    parse_confidence: str = "low"             # 'high', 'medium', 'low'
    missing_fields: List[str] = field(default_factory=list)  # What we couldn't extract


@dataclass
class ParseResult:
    """
    Result of parsing a message, which might contain multiple trades.
    """
    trades: List[ParsedTrade] = field(default_factory=list)
    raw_message: str = ""
    success: bool = False
    error_message: Optional[str] = None


def parse_message(text: str) -> ParseResult:
    """
    Parse a Telegram message and extract trade information.

    This is the main entry point for parsing.

    Args:
        text: The raw message text

    Returns:
        ParseResult with extracted trades (or error info)

    LEARNING MOMENT: Primary (Claude) vs Fallback (Regex) Parsing
    We try Claude API first because it handles any message format.
    If Claude fails (API error, no key, etc.), we fall back to regex patterns.
    """
    result = ParseResult(raw_message=text)

    if not text or not text.strip():
        result.error_message = "Empty message"
        return result

    # Try Claude API first (if available)
    if CLAUDE_AVAILABLE:
        try:
            claude_result = parse_with_claude(text)
            if claude_result:
                trade = convert_claude_to_parsed_trade(claude_result)
                result.trades.append(trade)
                result.success = True
                return result
        except Exception as e:
            logging.warning(f"Claude parsing failed, falling back to regex: {e}")

    # Fallback to regex parsing
    return parse_message_with_regex(text)


def convert_claude_to_parsed_trade(claude: 'ClaudeParsedTrade') -> ParsedTrade:
    """Convert Claude's parsed result to our ParsedTrade format."""
    trade = ParsedTrade(raw_message=claude.raw_message)

    trade.trade_type = claude.trade_type
    trade.token_symbol = claude.token_symbol
    trade.contract_address = claude.contract_address
    trade.chain = claude.chain
    trade.amount_spent = claude.amount_value
    trade.spend_currency = claude.amount_currency
    trade.market_cap = claude.market_cap
    trade.notes_url = claude.notes_url
    trade.dex_screener_url = claude.dex_screener_url

    # Perp-specific fields
    trade.is_perp = claude.venue_type == 'perp'
    trade.exchange = claude.exchange
    trade.position_type = claude.position_type

    trade.parse_confidence = 'high'

    return trade


def parse_message_with_regex(text: str) -> ParseResult:
    """
    Parse a message using regex patterns (fallback when Claude unavailable).
    """
    result = ParseResult(raw_message=text)

    # Check if this is a perp/futures trade first
    if is_perp_trade(text):
        trade = parse_perp_trade(text)
        result.trades.append(trade)
        result.success = True
        return result

    # Check if this is a CEX spot trade (e.g., "BTC Spot Binance")
    cex_spot = extract_cex_spot_info(text)
    if cex_spot:
        trade = parse_cex_spot_trade(text, cex_spot)
        result.trades.append(trade)
        result.success = True
        return result

    # Step 1: Find all contract addresses
    addresses = find_all_addresses(text)

    if not addresses:
        # No addresses found - might be an exit by ticker name
        trade = parse_single_trade(text, None)
        if trade.trade_type == 'SELL' and not trade.contract_address:
            # This might be an exit like "Sold PEPE"
            trade.missing_fields.append("contract_address")
            result.trades.append(trade)
            result.success = True
        else:
            result.error_message = "No contract address found. Please include the contract address or DEX Screener link."
        return result

    # Step 2: If multiple addresses, split message and parse each
    if len(addresses) == 1:
        trade = parse_single_trade(text, addresses[0])
        result.trades.append(trade)
    else:
        # Multiple addresses - try to parse each one
        for chain_info in addresses:
            trade = parse_single_trade(text, chain_info)
            result.trades.append(trade)

    result.success = True
    return result


def parse_perp_trade(text: str) -> ParsedTrade:
    """
    Parse a perp/futures trade message.

    These trades don't have contract addresses - just a symbol like "BTC" or "ETH".
    """
    trade = ParsedTrade(raw_message=text)
    trade.is_perp = True

    # Extract the symbol and position type
    perp_info = extract_perp_info(text)
    if perp_info:
        trade.token_symbol, trade.position_type = perp_info
    else:
        trade.missing_fields.append("token_symbol")

    # Detect exchange (defaults to hyperliquid for perps)
    trade.exchange = detect_exchange(text)
    trade.chain = trade.exchange  # For perps, "chain" is the exchange

    # Set trade type based on position
    trade_type = detect_trade_type(text)
    if trade_type:
        trade.trade_type = trade_type
    elif trade.position_type == 'SHORT':
        # Shorts are like sells (betting on price going down)
        trade.trade_type = 'SELL'
    else:
        trade.trade_type = 'BUY'  # Longs are like buys

    # Extract amounts
    usd_amounts = extract_usd_amounts(text)
    crypto_amounts = extract_crypto_amounts(text)

    if crypto_amounts:
        trade.amount_spent, trade.spend_currency = crypto_amounts[0]
    elif usd_amounts:
        trade.amount_spent = usd_amounts[0]
        trade.spend_currency = 'USD'
    else:
        trade.missing_fields.append("amount_spent")

    # Extract notes URL
    urls = extract_urls(text)
    if urls:
        trade.notes_url = urls[0]

    trade.parse_confidence = 'medium'

    return trade


def find_all_addresses(text: str) -> List[ChainInfo]:
    """
    Find all contract addresses in the message.
    Prioritizes DEX Screener links (most reliable) over raw addresses.

    Returns:
        List of ChainInfo objects with detected addresses
    """
    addresses = []

    # First, check for DEX Screener links (most reliable source of chain info)
    dex_info = extract_dexscreener_info(text)
    for chain, address in dex_info:
        chain_info = create_chain_info(address, chain=chain, from_dex_link=True)
        addresses.append(chain_info)

    # Keep track of addresses we've already found via DEX links
    found_addresses = {ci.address.lower() for ci in addresses}

    # Check for EVM addresses
    evm_addresses = extract_evm_addresses(text)
    text_chain = detect_chain_from_text(text)

    for addr in evm_addresses:
        if addr.lower() not in found_addresses:
            chain_info = create_chain_info(addr, chain=text_chain)
            addresses.append(chain_info)
            found_addresses.add(addr.lower())

    # Check for Solana addresses
    # Note: Solana address pattern can have false positives, so only add if
    # we have chain context suggesting Solana, or if no EVM addresses found
    if 'solana' in text.lower() or not evm_addresses:
        sol_addresses = extract_solana_addresses(text)
        for addr in sol_addresses:
            if addr.lower() not in found_addresses:
                # Extra validation: Solana addresses are usually 32-44 chars
                # and shouldn't look like words
                if len(addr) >= 32 and not addr.isalpha():
                    chain_info = create_chain_info(addr, chain='solana')
                    addresses.append(chain_info)
                    found_addresses.add(addr.lower())

    return addresses


def parse_single_trade(text: str, chain_info: Optional[ChainInfo]) -> ParsedTrade:
    """
    Parse a message for a single trade.

    Args:
        text: The message text
        chain_info: Optional ChainInfo for the contract address

    Returns:
        ParsedTrade with extracted information
    """
    trade = ParsedTrade(raw_message=text)

    # Set address and chain if provided
    if chain_info:
        trade.contract_address = chain_info.address
        trade.chain = chain_info.chain
        trade.parse_confidence = chain_info.confidence

    # Detect trade type (BUY or SELL)
    trade.trade_type = detect_trade_type(text)
    if not trade.trade_type:
        # Default to BUY if we have an address (most common case)
        if chain_info:
            trade.trade_type = 'BUY'
        trade.missing_fields.append("trade_type")

    # Extract amounts
    usd_amounts = extract_usd_amounts(text)
    crypto_amounts = extract_crypto_amounts(text)

    if crypto_amounts:
        # Prefer crypto amounts (e.g., "1.5K USDC")
        trade.amount_spent, trade.spend_currency = crypto_amounts[0]
    elif usd_amounts:
        # Fall back to USD amounts (e.g., "$100")
        trade.amount_spent = usd_amounts[0]
        trade.spend_currency = 'USD'
    else:
        trade.missing_fields.append("amount_spent")

    # Extract market cap
    trade.market_cap = extract_market_cap(text)

    # Extract thesis/notes URL
    urls = extract_urls(text)
    if urls:
        trade.notes_url = urls[0]  # Take first non-DEX-Screener URL

    # Check for DEX Screener URL
    dex_info = extract_dexscreener_info(text)
    if dex_info:
        # Reconstruct the URL
        chain, address = dex_info[0]
        trade.dex_screener_url = f"https://dexscreener.com/{chain}/{address}"

    return trade


def format_parse_summary(result: ParseResult) -> str:
    """
    Create a human-readable summary of what was parsed.
    Used for the bot's confirmation reply.

    Args:
        result: The ParseResult to summarize

    Returns:
        Formatted string for display
    """
    if not result.success:
        return f"Could not parse message: {result.error_message}"

    lines = []
    for i, trade in enumerate(result.trades, 1):
        if len(result.trades) > 1:
            lines.append(f"Trade {i}:")

        # Trade type
        type_emoji = "+" if trade.trade_type == 'BUY' else "-"
        lines.append(f"{type_emoji} {trade.trade_type or 'UNKNOWN'}")

        # Amount
        if trade.amount_spent:
            currency = trade.spend_currency or 'USD'
            lines.append(f"  Amount: {trade.amount_spent:,.2f} {currency}")

        # Token/Address
        if trade.contract_address:
            short_addr = f"{trade.contract_address[:6]}...{trade.contract_address[-4:]}"
            chain = trade.chain or 'unknown'
            lines.append(f"  Token: {short_addr} ({chain})")

        # Market cap
        if trade.market_cap:
            if trade.market_cap >= 1_000_000:
                mcap_str = f"${trade.market_cap / 1_000_000:.1f}M"
            else:
                mcap_str = f"${trade.market_cap / 1_000:,.0f}K"
            lines.append(f"  Entry MCAP: {mcap_str}")

        # Missing fields warning
        if trade.missing_fields:
            lines.append(f"  Missing: {', '.join(trade.missing_fields)}")

    return "\n".join(lines)
