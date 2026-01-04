#!/usr/bin/env python3
"""Full flow test - parsing + DEX Screener lookup."""

from parsing.message_parser import parse_message

# Direct DEX Screener API call (bypassing config)
import requests

def get_token_info_direct(contract_address):
    """Direct API call without config dependency."""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
    response = requests.get(url, timeout=10)
    data = response.json()
    pairs = data.get('pairs', [])
    if not pairs:
        return None
    # Get best pair by liquidity
    best = max(pairs, key=lambda p: p.get('liquidity', {}).get('usd', 0) or 0)
    return best

test_message = """0x20DD04c17AFD5c9a8b3f2cdacaa8Ee7907385BEF

Bought 1.5K USDC worth of this at $1.6M MCAP

Thesis https://members.delphidigital.io/feed/native-an-x402-blue-chip-in-the-making"""

print("=" * 60)
print("STEP 1: Parse the message")
print("=" * 60)

result = parse_message(test_message)
trade = result.trades[0]

print(f"Contract: {trade.contract_address}")
print(f"Chain guess: {trade.chain}")
print(f"Amount: {trade.amount_spent} {trade.spend_currency}")
print(f"Market cap: ${trade.market_cap:,.0f}")

print()
print("=" * 60)
print("STEP 2: Look up token on DEX Screener")
print("=" * 60)

try:
    pair = get_token_info_direct(trade.contract_address)
    if pair:
        base_token = pair.get('baseToken', {})
        price_usd = float(pair.get('priceUsd', 0))
        market_cap = pair.get('marketCap') or pair.get('fdv')
        chain = pair.get('chainId', 'unknown')

        print(f"Token found!")
        print(f"  Symbol: {base_token.get('symbol')}")
        print(f"  Name: {base_token.get('name')}")
        print(f"  Chain: {chain}")
        print(f"  Price: ${price_usd:.8f}")
        if market_cap:
            print(f"  Market Cap: ${market_cap:,.0f}")
        print(f"  DEX URL: https://dexscreener.com/{chain}/{pair.get('pairAddress')}")

        # Calculate tokens bought
        if price_usd and trade.amount_spent:
            tokens = trade.amount_spent / price_usd
            print()
            print(f"CALCULATION:")
            print(f"  ${trade.amount_spent:,.2f} / ${price_usd:.8f} = {tokens:,.2f} tokens")
    else:
        print("Token not found on DEX Screener")
except Exception as e:
    print(f"Error: {e}")
