"""
patterns.py - All regex patterns in one place

WHAT THIS FILE DOES:
Defines the patterns we use to extract structured data from your messages.
Having them all in one file makes it easy to add new patterns or debug issues.

LEARNING MOMENT: Regular Expressions (Regex)
Regex is a mini-language for describing text patterns. It looks cryptic at first,
but each piece has a meaning. Here's a decoder:

  .       = any single character
  *       = zero or more of the previous thing
  +       = one or more of the previous thing
  ?       = zero or one of the previous thing (optional)
  [abc]   = any character in the brackets (a, b, or c)
  [a-z]   = any character in the range (a through z)
  [^abc]  = any character NOT in the brackets
  \\d      = any digit (0-9)
  \\s      = any whitespace (space, tab, newline)
  \\b      = word boundary (start/end of a word)
  ^       = start of string
  $       = end of string
  (...)   = capture group (extract this part)
  (?:...) = non-capturing group (group but don't extract)
  |       = OR (either this or that)
  {n}     = exactly n of the previous thing
  {n,m}   = between n and m of the previous thing

Examples:
  0x[a-fA-F0-9]{40}
  └─┬─┘└────┬────┘└┬┘
    │       │      └── exactly 40 of these characters
    │       └── any hex character (0-9, a-f, A-F)
    └── literal "0x"

  \\$[\\d,]+
  └┬┘└──┬─┘
   │    └── one or more digits or commas
   └── literal "$" (backslash escapes special chars)
"""

import re
from typing import Optional, List, Tuple
from dataclasses import dataclass


# =============================================================================
# CONTRACT ADDRESS PATTERNS
# =============================================================================

# EVM addresses (Ethereum, Base, BNB, Arbitrum, etc.)
# Format: 0x followed by exactly 40 hexadecimal characters
# Example: 0x20DD04c17AFD5c9a8b3f2cdacaa8Ee7907385BEF
EVM_ADDRESS_PATTERN = re.compile(r'0x[a-fA-F0-9]{40}', re.IGNORECASE)

# Solana addresses
# Format: 32-44 base58 characters (no 0, O, I, l to avoid confusion)
# Example: 7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr
# Note: This can match some non-address strings, so we validate via API
SOLANA_ADDRESS_PATTERN = re.compile(r'[1-9A-HJ-NP-Za-km-z]{32,44}')


# =============================================================================
# DEX SCREENER LINK PATTERN
# =============================================================================

# Matches DEX Screener URLs and extracts the chain and address
# Format: https://dexscreener.com/{chain}/{address}
# Example: https://dexscreener.com/ethereum/0x6982508145454ce325ddbe47a25d4ec3d2311933
DEXSCREENER_PATTERN = re.compile(
    r'(?:https?://)?dexscreener\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9]+)',
    re.IGNORECASE
)


# =============================================================================
# AMOUNT PATTERNS
# =============================================================================

# Dollar amounts with optional K/M suffix
# Matches: $100, $1,500, $1.5K, $2.3M, $50.50
USD_AMOUNT_PATTERN = re.compile(
    r'\$\s*([\d,]+(?:\.\d+)?)\s*([KkMmBb])?',
    re.IGNORECASE
)

# Crypto amounts with currency (including K/M suffix)
# Matches: 0.5 ETH, 100 SOL, 1.5K USDC, 2000 USDT, 1.5M USDC
CRYPTO_AMOUNT_PATTERN = re.compile(
    r'([\d,]+(?:\.\d+)?)\s*([KkMmBb])?\s*(ETH|SOL|BTC|USDC|USDT|BNB|MATIC|AVAX|FTM)',
    re.IGNORECASE
)

# Generic number with K/M/B suffix (for market cap, etc.)
# Matches: 1.5K, 2.3M, 100M, 1B
NUMBER_WITH_SUFFIX_PATTERN = re.compile(
    r'([\d,]+(?:\.\d+)?)\s*([KkMmBb])',
    re.IGNORECASE
)


# =============================================================================
# MARKET CAP PATTERN
# =============================================================================

# Matches market cap mentions
# Matches: $1.6M MCAP, $500K mcap, 2M market cap, at 1.5M mc
MARKET_CAP_PATTERN = re.compile(
    r'(?:\$\s*)?([\d,]+(?:\.\d+)?)\s*([KkMmBb])?\s*(?:mcap|mc|market\s*cap)',
    re.IGNORECASE
)


# =============================================================================
# TRADE TYPE PATTERNS
# =============================================================================

# Keywords indicating a BUY
BUY_KEYWORDS_PATTERN = re.compile(
    r'\b(bought|buy|buying|entered|entry|ape|aped|aping|grabbed|sniped|sniping|longed|long|in|added)\b',
    re.IGNORECASE
)

# Keywords indicating a SELL
SELL_KEYWORDS_PATTERN = re.compile(
    r'\b(sold|sell|selling|exit|exited|exiting|out|dumped|took\s*profit|tp|closed|shorte?d?)\b',
    re.IGNORECASE
)


# =============================================================================
# URL PATTERN
# =============================================================================

# General URL pattern for thesis links, etc.
# Matches most URLs starting with http:// or https://
URL_PATTERN = re.compile(
    r'https?://[^\s<>"{}|\\^`\[\]]+',
    re.IGNORECASE
)


# =============================================================================
# PERPS / DERIVATIVES PATTERNS
# =============================================================================

# LEARNING MOMENT: What are Perps?
# "Perps" (perpetual futures) are derivatives that let you trade with leverage.
# Unlike spot trades (buying the actual token), perps are contracts that track
# the price. You can go "long" (bet price goes up) or "short" (bet price goes down).
# Common platforms: Hyperliquid, Binance Futures, dYdX, GMX

# Matches perp/futures mentions
# Matches: BTC perps, ETH perp, BTC perpetual, ETH futures
PERP_PATTERN = re.compile(
    r'\b([A-Z]{2,10})\s*(?:perps?|perpetuals?|futures?)\b',
    re.IGNORECASE
)

# Common perp trading symbols (tokens commonly traded as perps)
# These are used when someone just says "ETH Hyperliquid" without "perps"
COMMON_PERP_SYMBOLS = {
    # Major coins
    'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'MATIC', 'DOT', 'LINK',
    # L2s and newer L1s
    'ARB', 'OP', 'APT', 'SUI', 'SEI', 'TIA', 'INJ', 'NEAR', 'FTM',
    # DeFi
    'UNI', 'AAVE', 'CRV', 'LDO', 'MKR', 'SNX', 'DYDX', 'GMX',
    # Memes
    'DOGE', 'SHIB', 'PEPE', 'WIF', 'BONK', 'FLOKI',
    # Solana ecosystem
    'JTO', 'JUP', 'PYTH', 'RAY', 'ORCA',
    # Hyperliquid specific
    'HYPE', 'PURR',
}

# Pattern to detect "Spot" trades (CEX spot, not perps)
SPOT_PATTERN = re.compile(r'\bspot\b', re.IGNORECASE)

# Pattern to match symbol + exchange (e.g., "ETH Hyperliquid", "BTC on HL")
SYMBOL_EXCHANGE_PATTERN = re.compile(
    r'\b([A-Z]{2,10})\s+(?:on\s+)?(?:hyperliquid|hl|binance|bybit|dydx|gmx)\b',
    re.IGNORECASE
)

# Exchange/platform patterns
EXCHANGE_PATTERNS = {
    'hyperliquid': re.compile(r'\b(?:hyperliquid|hl)\b', re.IGNORECASE),
    'binance': re.compile(r'\b(?:binance|binance\s*futures?|binance\s*perps?)\b', re.IGNORECASE),
    'bybit': re.compile(r'\b(?:bybit)\b', re.IGNORECASE),
    'dydx': re.compile(r'\b(?:dydx)\b', re.IGNORECASE),
    'gmx': re.compile(r'\b(?:gmx)\b', re.IGNORECASE),
}

# Trade type for perps (long/short)
LONG_PATTERN = re.compile(r'\b(?:longe?d?|long)\b', re.IGNORECASE)
SHORT_PATTERN = re.compile(r'\b(?:shorte?d?|short)\b', re.IGNORECASE)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_number_with_suffix(value: str, suffix: Optional[str] = None) -> float:
    """
    Parse a number that might have K/M/B suffix.

    Args:
        value: The numeric part (e.g., "1.5", "1,500")
        suffix: Optional suffix (K, M, B)

    Returns:
        The actual number (e.g., 1500.0 for "1.5K")

    Examples:
        parse_number_with_suffix("1.5", "K") -> 1500.0
        parse_number_with_suffix("1,500", None) -> 1500.0
        parse_number_with_suffix("2.3", "M") -> 2300000.0
    """
    # Remove commas from the number
    clean_value = value.replace(",", "")
    number = float(clean_value)

    if suffix:
        suffix = suffix.upper()
        multipliers = {
            'K': 1_000,
            'M': 1_000_000,
            'B': 1_000_000_000,
        }
        number *= multipliers.get(suffix, 1)

    return number


def extract_evm_addresses(text: str) -> List[str]:
    """Extract all EVM (Ethereum-style) addresses from text."""
    return EVM_ADDRESS_PATTERN.findall(text)


def extract_solana_addresses(text: str) -> List[str]:
    """
    Extract potential Solana addresses from text.
    Note: May include false positives; validate via API.
    """
    return SOLANA_ADDRESS_PATTERN.findall(text)


def extract_dexscreener_info(text: str) -> List[Tuple[str, str]]:
    """
    Extract DEX Screener chain and address from URLs.

    Returns:
        List of (chain, address) tuples
    """
    return DEXSCREENER_PATTERN.findall(text)


def extract_usd_amounts(text: str) -> List[float]:
    """
    Extract USD amounts from text.

    Returns:
        List of amounts in USD (suffixes already applied)
    """
    amounts = []
    for match in USD_AMOUNT_PATTERN.finditer(text):
        value, suffix = match.groups()
        amounts.append(parse_number_with_suffix(value, suffix))
    return amounts


def extract_crypto_amounts(text: str) -> List[Tuple[float, str]]:
    """
    Extract crypto amounts with their currency.

    Returns:
        List of (amount, currency) tuples
    """
    amounts = []
    for match in CRYPTO_AMOUNT_PATTERN.finditer(text):
        value, suffix, currency = match.groups()
        amount = parse_number_with_suffix(value, suffix)
        amounts.append((amount, currency.upper()))
    return amounts


def extract_market_cap(text: str) -> Optional[float]:
    """
    Extract market cap from text.

    Returns:
        Market cap in USD, or None if not found
    """
    match = MARKET_CAP_PATTERN.search(text)
    if match:
        value, suffix = match.groups()
        return parse_number_with_suffix(value, suffix)
    return None


def detect_trade_type(text: str) -> Optional[str]:
    """
    Detect if the message is about buying or selling.

    Returns:
        'BUY', 'SELL', or None if unclear
    """
    has_buy = BUY_KEYWORDS_PATTERN.search(text) is not None
    has_sell = SELL_KEYWORDS_PATTERN.search(text) is not None

    if has_buy and not has_sell:
        return 'BUY'
    elif has_sell and not has_buy:
        return 'SELL'
    elif has_buy and has_sell:
        # Both keywords present - check which comes first
        buy_match = BUY_KEYWORDS_PATTERN.search(text)
        sell_match = SELL_KEYWORDS_PATTERN.search(text)
        if buy_match and sell_match:
            return 'BUY' if buy_match.start() < sell_match.start() else 'SELL'
    return None


def extract_urls(text: str) -> List[str]:
    """
    Extract all URLs from text (excluding DEX Screener links which are handled separately).
    """
    all_urls = URL_PATTERN.findall(text)
    # Filter out DEX Screener links
    return [url for url in all_urls if 'dexscreener.com' not in url.lower()]


def extract_perp_info(text: str) -> Optional[Tuple[str, str]]:
    """
    Extract perp/futures trade info from text.

    Returns:
        Tuple of (symbol, position_type) like ('BTC', 'LONG') or None

    Handles two cases:
    1. Explicit: "BTC perps" or "ETH futures"
    2. Implicit: "ETH Hyperliquid" or "long BTC on HL" (exchange mentioned with symbol)
    """
    symbol = None

    # First, try explicit perp pattern (e.g., "BTC perps")
    match = PERP_PATTERN.search(text)
    if match:
        symbol = match.group(1).upper()
    else:
        # Try symbol + exchange pattern (e.g., "ETH Hyperliquid")
        match = SYMBOL_EXCHANGE_PATTERN.search(text)
        if match:
            potential_symbol = match.group(1).upper()
            # Only accept if it's a common perp symbol to avoid false positives
            if potential_symbol in COMMON_PERP_SYMBOLS:
                symbol = potential_symbol

    if symbol:
        # Determine if long or short
        if SHORT_PATTERN.search(text):
            position_type = 'SHORT'
        else:
            position_type = 'LONG'  # Default to long
        return (symbol, position_type)

    return None


def detect_exchange(text: str) -> Optional[str]:
    """
    Detect which exchange/platform is mentioned.

    Returns:
        Exchange name like 'hyperliquid', 'binance', etc. or None
        Defaults to 'hyperliquid' if perps mentioned but no exchange specified.
    """
    for exchange, pattern in EXCHANGE_PATTERNS.items():
        if pattern.search(text):
            return exchange

    # If perp mentioned but no exchange, default to hyperliquid
    if PERP_PATTERN.search(text):
        return 'hyperliquid'

    return None


def is_spot_trade(text: str) -> bool:
    """Check if this is explicitly a spot trade (not perps)."""
    return SPOT_PATTERN.search(text) is not None


def is_perp_trade(text: str) -> bool:
    """
    Check if this message is about a perp/futures trade.

    Returns True if:
    1. Explicit perp keywords: "BTC perps", "ETH futures"
    2. Symbol + exchange combo: "ETH Hyperliquid", "BTC on HL" (but NOT if "spot" mentioned)
    """
    # If "spot" is mentioned, it's NOT a perp trade
    if is_spot_trade(text):
        return False

    # Check for explicit perp keywords
    if PERP_PATTERN.search(text):
        return True

    # Check for symbol + exchange pattern
    match = SYMBOL_EXCHANGE_PATTERN.search(text)
    if match:
        symbol = match.group(1).upper()
        if symbol in COMMON_PERP_SYMBOLS:
            return True

    return False


def extract_cex_spot_info(text: str) -> Optional[Tuple[str, str]]:
    """
    Extract CEX spot trade info (e.g., "BTC Spot Binance").

    Returns:
        Tuple of (symbol, exchange) like ('BTC', 'binance') or None
    """
    if not is_spot_trade(text):
        return None

    # Look for symbol + exchange pattern
    match = SYMBOL_EXCHANGE_PATTERN.search(text)
    if match:
        symbol = match.group(1).upper()
        if symbol in COMMON_PERP_SYMBOLS:  # Reuse the symbol list
            exchange = detect_exchange(text)
            return (symbol, exchange)

    return None
