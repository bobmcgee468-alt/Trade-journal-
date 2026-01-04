"""
dex_screener.py - Fetch token data from DEX Screener API

WHAT THIS FILE DOES:
Queries the DEX Screener API to get:
- Current token price in USD
- Token symbol and name
- Which chain the token is on (for EVM addresses)
- Liquidity and volume info

LEARNING MOMENT: APIs and HTTP Requests
An API (Application Programming Interface) is a way for programs to talk to each other.
DEX Screener provides a REST API - you send an HTTP request to a URL, and they
send back data in JSON format.

Example flow:
1. We send: GET https://api.dexscreener.com/token-pairs/v1/ethereum/0x123...
2. They respond with JSON containing price, symbol, liquidity, etc.
3. We parse the JSON into Python objects

LEARNING MOMENT: Rate Limiting
APIs often limit how many requests you can make per minute. DEX Screener allows
300 requests/minute, which is plenty for a personal trade journal. If you exceed
the limit, you'll get a 429 "Too Many Requests" error.
"""

import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DEXSCREENER_API_BASE


@dataclass
class TokenInfo:
    """Information about a token from DEX Screener."""
    contract_address: str
    chain: str
    symbol: str
    name: str
    price_usd: Optional[float]
    market_cap: Optional[float]
    liquidity_usd: Optional[float]
    volume_24h: Optional[float]
    price_change_24h: Optional[float]
    dex_url: str


class DexScreenerError(Exception):
    """Custom exception for DEX Screener API errors."""
    pass


# Chain priority order - lower index = higher priority
# Solana first for Solana addresses, then Base > BNB > Ethereum for EVM
CHAIN_PRIORITY = {
    'solana': 0,
    'base': 1,
    'bsc': 2,       # BNB Chain
    'ethereum': 3,
}
# Chains not in this list get priority 100 (lowest)
DEFAULT_CHAIN_PRIORITY = 100


def get_chain_priority(chain_id: str) -> int:
    """Get the priority score for a chain (lower = more preferred)."""
    return CHAIN_PRIORITY.get(chain_id.lower(), DEFAULT_CHAIN_PRIORITY)


def get_token_info(contract_address: str, chain: Optional[str] = None) -> Optional[TokenInfo]:
    """
    Get token information from DEX Screener.

    Args:
        contract_address: The token's contract address
        chain: Optional chain hint (if provided, strongly prefer this chain)

    Returns:
        TokenInfo if found, None if not found

    Raises:
        DexScreenerError: If API request fails

    LEARNING MOMENT: Chain Selection Strategy
    When the same token exists on multiple chains (common for popular tokens),
    we need to pick the "right" one. Our strategy:
    1. If user specified a chain, use that chain if found
    2. Otherwise, use chain priority: Solana > Base > BNB > Ethereum
    3. Within same priority, prefer higher liquidity (more reliable price)
    """
    # Try to find the token
    pairs = search_token(contract_address, chain)

    if not pairs:
        return None

    # If user specified a chain, try to find it on that chain first
    if chain:
        chain_pairs = [p for p in pairs if p.get('chainId', '').lower() == chain.lower()]
        if chain_pairs:
            # Found on specified chain - use highest liquidity pair on that chain
            best_pair = max(chain_pairs, key=lambda p: p.get('liquidity', {}).get('usd', 0) or 0)
            return parse_pair_to_token_info(best_pair, contract_address)

    # No chain specified or not found on specified chain
    # Sort by: 1) chain priority, 2) liquidity within same priority
    def pair_score(p):
        chain_id = p.get('chainId', 'unknown')
        priority = get_chain_priority(chain_id)
        liquidity = p.get('liquidity', {}).get('usd', 0) or 0
        # Return tuple: (priority, -liquidity) so we sort ascending
        # Lower priority number = better, higher liquidity = better
        return (priority, -liquidity)

    pairs_sorted = sorted(pairs, key=pair_score)
    best_pair = pairs_sorted[0]

    return parse_pair_to_token_info(best_pair, contract_address)


def search_token(contract_address: str, chain: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search for a token across DEX Screener.

    Always searches all chains first (most reliable), then filters by chain if specified.
    This ensures we find tokens even when we guess the wrong chain.

    Returns:
        List of pair data dictionaries
    """
    # Always search all chains - more reliable than guessing
    url = f"{DEXSCREENER_API_BASE}/latest/dex/tokens/{contract_address}"

    try:
        response = requests.get(url, timeout=10)

        # Handle rate limiting
        if response.status_code == 429:
            raise DexScreenerError("Rate limited by DEX Screener. Please wait a moment.")

        # Handle not found
        if response.status_code == 404:
            return []

        response.raise_for_status()
        data = response.json()

        # API returns 'pairs' array for token search, or direct array for chain search
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'pairs' in data:
            return data['pairs'] or []
        else:
            return []

    except requests.exceptions.Timeout:
        raise DexScreenerError("DEX Screener API timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        raise DexScreenerError(f"Failed to fetch from DEX Screener: {str(e)}")


def get_pair_info(pair_address: str, chain: str) -> Optional[TokenInfo]:
    """
    Get token info from a pair address (used when parsing DEX Screener URLs).

    LEARNING MOMENT: Token Address vs Pair Address
    DEX Screener URLs can contain either:
    - Token address: The actual token contract (0x...)
    - Pair address: A liquidity pool contract (TOKEN/WETH pair)

    When someone shares a DEX Screener link, it usually contains the pair address.
    We need to fetch the pair, then extract the base token info.
    """
    url = f"{DEXSCREENER_API_BASE}/latest/dex/pairs/{chain}/{pair_address}"

    try:
        response = requests.get(url, timeout=10)

        if response.status_code == 429:
            raise DexScreenerError("Rate limited by DEX Screener. Please wait a moment.")

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()

        # The pairs endpoint returns a 'pair' object directly
        pair = data.get('pair') if isinstance(data, dict) else None
        if not pair:
            return None

        # Extract the base token (the token being traded, not WETH/USDC)
        base_token = pair.get('baseToken', {})
        token_address = base_token.get('address', pair_address)

        return parse_pair_to_token_info(pair, token_address)

    except requests.exceptions.Timeout:
        raise DexScreenerError("DEX Screener API timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        raise DexScreenerError(f"Failed to fetch from DEX Screener: {str(e)}")


def parse_pair_to_token_info(pair: Dict[str, Any], contract_address: str) -> TokenInfo:
    """
    Convert a DEX Screener pair response to our TokenInfo format.

    LEARNING MOMENT: JSON Parsing
    The API returns nested JSON. We use .get() with defaults to safely
    access nested fields without crashing if they're missing.
    """
    # Determine which token in the pair is ours
    base_token = pair.get('baseToken', {})
    quote_token = pair.get('quoteToken', {})

    # Our token is usually the base token, but check to be sure
    if base_token.get('address', '').lower() == contract_address.lower():
        token = base_token
    else:
        token = quote_token

    # Build the DEX Screener URL
    chain = pair.get('chainId', 'unknown')
    pair_address = pair.get('pairAddress', contract_address)
    dex_url = f"https://dexscreener.com/{chain}/{pair_address}"

    # Extract price - it's a string in the API, convert to float
    price_str = pair.get('priceUsd')
    price_usd = float(price_str) if price_str else None

    # Extract other metrics
    liquidity = pair.get('liquidity', {})
    volume = pair.get('volume', {})
    price_change = pair.get('priceChange', {})

    return TokenInfo(
        contract_address=token.get('address', contract_address),
        chain=chain,
        symbol=token.get('symbol', 'UNKNOWN'),
        name=token.get('name', 'Unknown Token'),
        price_usd=price_usd,
        market_cap=pair.get('marketCap') or pair.get('fdv'),  # Use FDV if mcap not available
        liquidity_usd=liquidity.get('usd'),
        volume_24h=volume.get('h24'),
        price_change_24h=price_change.get('h24'),
        dex_url=dex_url
    )


def calculate_tokens_from_spend(
    amount_spent: float,
    spend_currency: str,
    token_info: TokenInfo
) -> Optional[float]:
    """
    Calculate how many tokens were bought based on spend amount and price.

    Args:
        amount_spent: Amount spent (e.g., 1500 for "1.5K USDC")
        spend_currency: Currency spent (USD, USDC, ETH, SOL, etc.)
        token_info: Token information with current price

    Returns:
        Number of tokens, or None if can't calculate
    """
    if not token_info.price_usd or token_info.price_usd == 0:
        return None

    # If spent in USD or stablecoins, straightforward calculation
    usd_currencies = {'USD', 'USDC', 'USDT', 'DAI', 'BUSD'}

    if spend_currency.upper() in usd_currencies:
        return amount_spent / token_info.price_usd

    # For crypto currencies, we'd need to look up their USD price too
    # For now, return None and log that we need the price
    # TODO: Add lookup for ETH, SOL, etc. prices
    return None


# Simple test when running this file directly
if __name__ == "__main__":
    # Test with a known token (PEPE on Ethereum)
    test_address = "0x6982508145454Ce325dDbE47a25d4ec3d2311933"

    print(f"Looking up token: {test_address}")
    try:
        info = get_token_info(test_address)
        if info:
            print(f"Found: {info.symbol} ({info.name})")
            print(f"Chain: {info.chain}")
            print(f"Price: ${info.price_usd}")
            print(f"Market Cap: ${info.market_cap:,.0f}" if info.market_cap else "Market Cap: N/A")
            print(f"URL: {info.dex_url}")
        else:
            print("Token not found")
    except DexScreenerError as e:
        print(f"Error: {e}")
