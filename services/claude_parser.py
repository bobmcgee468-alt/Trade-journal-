"""
claude_parser.py - Use Claude API to parse trade messages

WHAT THIS FILE DOES:
Instead of complex regex patterns, we send the message to Claude and ask it
to extract structured trade data. This handles any format naturally.

LEARNING MOMENT: LLM for Structured Data Extraction
This is a common pattern: use an LLM to convert unstructured text into structured data.
The key is a clear prompt that specifies exactly what fields you want and their format.

We use Claude Haiku (the smallest/cheapest model) because:
1. This is a simple extraction task, doesn't need the smartest model
2. Haiku is ~10x cheaper than Sonnet (~$0.00025 per message vs $0.003)
3. Haiku is faster (lower latency)

Cost estimate: 300 trades/month * $0.00025 = $0.075/month
"""

import json
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from config import ANTHROPIC_API_KEY


@dataclass
class ClaudeParsedTrade:
    """Structured trade data extracted by Claude."""
    # Trade type
    trade_type: str  # 'BUY' or 'SELL'

    # Asset identification
    token_symbol: Optional[str] = None      # e.g., 'BTC', 'ETH', 'PEPE'
    contract_address: Optional[str] = None  # e.g., '0x123...'
    chain: Optional[str] = None             # e.g., 'base', 'solana', 'ethereum'

    # Trade venue
    venue_type: str = 'spot'                # 'spot', 'perp', 'futures'
    exchange: Optional[str] = None          # e.g., 'hyperliquid', 'binance'
    leverage: Optional[str] = None          # e.g., '3x', '10x'
    position_type: Optional[str] = None     # 'LONG' or 'SHORT' for perps

    # Amounts
    amount_value: Optional[float] = None    # The numeric amount
    amount_currency: Optional[str] = None   # e.g., 'USD', 'USDC', 'ETH'

    # Context
    market_cap: Optional[float] = None      # Market cap at trade time
    notes_url: Optional[str] = None         # Any URL in the message
    dex_screener_url: Optional[str] = None  # DEX Screener link if present

    # Raw
    raw_message: str = ""
    parse_confidence: str = "high"


# The prompt that tells Claude how to parse trade messages
PARSE_PROMPT = """You are a trade message parser. Extract structured data from trading messages.

IMPORTANT RULES:
1. For contract addresses: Extract the full address (0x... for EVM, base58 for Solana)
2. For chains: Use lowercase (ethereum, base, solana, bsc, arbitrum)
3. For exchanges: hyperliquid, binance, bybit, dydx, gmx (these are NOT chains)
4. CRITICAL - Amount suffixes:
   - K = thousand (multiply by 1,000): $10K = 10000, $100K = 100000, 1.5K = 1500
   - M = million (multiply by 1,000,000): $1M = 1000000, $2.5M = 2500000
   - B = billion (multiply by 1,000,000,000): $1B = 1000000000
   Examples: "100K" = 100000, "$1.5K USDC" = 1500 USDC, "10K" = 10000
5. For DEX Screener links: Extract both the chain and address from the URL
6. For perps/futures: Set venue_type to 'perp', extract leverage if mentioned
7. Default trade_type to 'BUY' unless sell/exit/short keywords present
8. For "spot" trades on CEX: venue_type is 'spot', exchange is the CEX name
9. IMPORTANT: Extract the token symbol even for perp trades. Common perp symbols:
   BTC, ETH, SOL, HYPE, ARB, OP, DOGE, WIF, BONK, PEPE, SUI, APT, TIA, etc.
   In "100K hype 3x hyperliquid", the symbol is HYPE (not hyperliquid).
10. For amounts like "10K BTC" or "100K hype": this means USD value, so:
    amount_value: the number (10000 or 100000), amount_currency: "USD"

Chain priority hints (when not specified):
- If DEX Screener link: use chain from URL
- If Solana-format address: chain is 'solana'
- If EVM address without context: likely 'base' (popular for new memecoins)
- Hyperliquid/Binance/Bybit: these are exchanges, not chains

Return a JSON object with these fields:
{
  "trade_type": "BUY" or "SELL",
  "token_symbol": "BTC" or null,
  "contract_address": "0x..." or null,
  "chain": "base" or null,
  "venue_type": "spot" or "perp",
  "exchange": "hyperliquid" or null,
  "leverage": "3x" or null,
  "position_type": "LONG" or "SHORT" or null,
  "amount_value": 1500.0 or null,
  "amount_currency": "USDC" or null,
  "market_cap": 1600000.0 or null,
  "notes_url": "https://..." or null,
  "dex_screener_url": "https://dexscreener.com/..." or null
}

Only return the JSON object, no other text."""


def parse_with_claude(message: str) -> Optional[ClaudeParsedTrade]:
    """
    Parse a trade message using Claude API.

    Args:
        message: The raw trade message

    Returns:
        ClaudeParsedTrade if successful, None if parsing fails
    """
    if not ANTHROPIC_AVAILABLE:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in environment")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",  # Cheapest, fastest model
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": f"{PARSE_PROMPT}\n\nMessage to parse:\n{message}"
                }
            ]
        )

        # Extract the JSON from the response
        response_text = response.content[0].text.strip()

        # Parse the JSON
        data = json.loads(response_text)

        # Convert to our dataclass
        return ClaudeParsedTrade(
            trade_type=data.get('trade_type', 'BUY'),
            token_symbol=data.get('token_symbol'),
            contract_address=data.get('contract_address'),
            chain=data.get('chain'),
            venue_type=data.get('venue_type', 'spot'),
            exchange=data.get('exchange'),
            leverage=data.get('leverage'),
            position_type=data.get('position_type'),
            amount_value=data.get('amount_value'),
            amount_currency=data.get('amount_currency'),
            market_cap=data.get('market_cap'),
            notes_url=data.get('notes_url'),
            dex_screener_url=data.get('dex_screener_url'),
            raw_message=message,
            parse_confidence='high'
        )

    except json.JSONDecodeError as e:
        print(f"Failed to parse Claude response as JSON: {e}")
        print(f"Response was: {response_text}")
        return None
    except Exception as e:
        print(f"Claude API error: {e}")
        return None


# Test when running directly
if __name__ == "__main__":
    test_messages = [
        "100K hype 3x hyperliquid",
        "$1.5K USDC on https://dexscreener.com/base/0x4cd15f2bc9533bf6fac4ae33c649f138cb601935",
        "10K BTC Spot Binance",
        "Long ETH on HL $500",
        "Bought 1K USDC of 0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed at 50M mcap",
    ]

    print("Testing Claude Parser\n" + "="*50)

    for msg in test_messages:
        print(f"\nMessage: \"{msg}\"")
        print("-" * 40)

        result = parse_with_claude(msg)
        if result:
            print(f"  trade_type: {result.trade_type}")
            print(f"  symbol: {result.token_symbol}")
            print(f"  venue: {result.venue_type} @ {result.exchange}")
            if result.leverage:
                print(f"  leverage: {result.leverage}")
            if result.contract_address:
                print(f"  address: {result.contract_address[:20]}...")
            print(f"  chain: {result.chain}")
            print(f"  amount: {result.amount_value} {result.amount_currency}")
        else:
            print("  FAILED to parse")
