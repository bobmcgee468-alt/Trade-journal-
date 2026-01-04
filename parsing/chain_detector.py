"""
chain_detector.py - Detect which blockchain a contract address is on

WHAT THIS FILE DOES:
Given a contract address, figures out which blockchain it's on.
This is trickier than it sounds because:
1. EVM addresses (0x...) look the same on Ethereum, Base, BNB, etc.
2. We need to query DEX Screener to find where the token actually trades
3. Solana addresses have a different format entirely

LEARNING MOMENT: Address Formats by Chain
- EVM chains (Ethereum, Base, BNB, Arbitrum, Polygon, etc.):
  All use 0x + 40 hex characters. You can't tell which chain just by looking.

- Solana:
  Uses Base58 encoding (32-44 characters, no 0/O/I/l to avoid confusion)

- Other chains we might support:
  - Hyperliquid: Uses EVM-style addresses
  - TON: Different format entirely (will add if needed)
"""

from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class ChainInfo:
    """Information about a detected chain and address."""
    chain: str              # Chain identifier (e.g., 'ethereum', 'solana', 'base')
    address: str            # The contract address
    address_type: str       # 'evm' or 'solana' or 'unknown'
    confidence: str         # 'high' (from DEX link), 'medium' (format match), 'low' (guess)


# EVM-compatible chains and their DEX Screener identifiers
EVM_CHAINS = {
    'ethereum': 'ethereum',
    'eth': 'ethereum',
    'base': 'base',
    'bsc': 'bsc',
    'bnb': 'bsc',
    'binance': 'bsc',
    'arbitrum': 'arbitrum',
    'arb': 'arbitrum',
    'polygon': 'polygon',
    'matic': 'polygon',
    'optimism': 'optimism',
    'op': 'optimism',
    'avalanche': 'avalanche',
    'avax': 'avalanche',
    'fantom': 'fantom',
    'ftm': 'fantom',
    'zksync': 'zksync',
    'linea': 'linea',
    'blast': 'blast',
    'hyperliquid': 'hyperliquid',
    'hl': 'hyperliquid',
}

# Normalize chain names to DEX Screener format
def normalize_chain_name(chain: str) -> str:
    """
    Convert various chain names to the DEX Screener API format.

    Examples:
        'eth' -> 'ethereum'
        'bnb' -> 'bsc'
        'arb' -> 'arbitrum'
    """
    return EVM_CHAINS.get(chain.lower(), chain.lower())


def detect_address_type(address: str) -> str:
    """
    Detect what type of address this is based on format.

    Returns:
        'evm' - Ethereum-style address (0x...)
        'solana' - Solana-style address (base58)
        'unknown' - Can't determine
    """
    # EVM: starts with 0x, exactly 42 characters total
    if address.startswith('0x') and len(address) == 42:
        # Verify it's valid hex
        try:
            int(address[2:], 16)
            return 'evm'
        except ValueError:
            pass

    # Solana: 32-44 base58 characters
    # Base58 alphabet: 123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz
    base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
    if 32 <= len(address) <= 44 and all(c in base58_chars for c in address):
        return 'solana'

    return 'unknown'


def detect_chain_from_text(text: str) -> Optional[str]:
    """
    Try to detect chain from text context (not the address itself).

    Looks for chain mentions like "on Base", "Solana", etc.

    Returns:
        Normalized chain name or None
    """
    text_lower = text.lower()

    # Check for explicit chain mentions
    chain_mentions = [
        ('solana', 'solana'),
        ('on sol', 'solana'),
        ('ethereum', 'ethereum'),
        ('on eth', 'ethereum'),
        ('mainnet', 'ethereum'),  # Usually means Ethereum mainnet
        ('base', 'base'),
        ('on base', 'base'),
        ('bsc', 'bsc'),
        ('bnb', 'bsc'),
        ('binance', 'bsc'),
        ('arbitrum', 'arbitrum'),
        ('arb', 'arbitrum'),
        ('polygon', 'polygon'),
        ('hyperliquid', 'hyperliquid'),
        ('on hl', 'hyperliquid'),
    ]

    for keyword, chain in chain_mentions:
        if keyword in text_lower:
            return chain

    return None


def create_chain_info(
    address: str,
    chain: Optional[str] = None,
    from_dex_link: bool = False
) -> ChainInfo:
    """
    Create a ChainInfo object with detected information.

    Args:
        address: The contract address
        chain: Known chain (from DEX link or text context)
        from_dex_link: Whether the chain was extracted from a DEX Screener link

    Returns:
        ChainInfo with all detected information
    """
    address_type = detect_address_type(address)

    # Determine confidence
    if from_dex_link:
        confidence = 'high'  # DEX links are definitive
    elif chain:
        confidence = 'medium'  # Chain detected from context
    else:
        confidence = 'low'  # Just guessing from address format

    # If no chain specified, guess from address type
    # LEARNING MOMENT: Default Chain Selection
    # We default EVM addresses to 'base' because in the user's trading context,
    # Base is more likely than Ethereum for new token trades. The DEX Screener
    # lookup will verify and correct this if needed (it searches all chains).
    if not chain:
        if address_type == 'solana':
            chain = 'solana'
        elif address_type == 'evm':
            chain = 'base'  # Default EVM to Base (most common for user's trades)
        else:
            chain = 'unknown'
    else:
        chain = normalize_chain_name(chain)

    return ChainInfo(
        chain=chain,
        address=address,
        address_type=address_type,
        confidence=confidence
    )
