#!/usr/bin/env python3
"""Quick test script to verify parsing works."""

from parsing.message_parser import parse_message, format_parse_summary
from parsing.patterns import (
    extract_evm_addresses,
    extract_usd_amounts,
    extract_crypto_amounts,
    extract_market_cap,
    detect_trade_type,
    extract_urls,
)

# Your example message
test_message = """0x20DD04c17AFD5c9a8b3f2cdacaa8Ee7907385BEF

Bought 1.5K USDC worth of this at $1.6M MCAP

Thesis https://members.delphidigital.io/feed/native-an-x402-blue-chip-in-the-making"""

print("=" * 60)
print("INPUT MESSAGE:")
print("=" * 60)
print(test_message)
print()

print("=" * 60)
print("STEP-BY-STEP EXTRACTION:")
print("=" * 60)

# Test each pattern individually
print(f"\n1. EVM Addresses found: {extract_evm_addresses(test_message)}")
print(f"2. Trade type detected: {detect_trade_type(test_message)}")
print(f"3. USD amounts: {extract_usd_amounts(test_message)}")
print(f"4. Crypto amounts: {extract_crypto_amounts(test_message)}")
print(f"5. Market cap: {extract_market_cap(test_message)}")
print(f"6. URLs (non-DEX): {extract_urls(test_message)}")

print()
print("=" * 60)
print("FULL PARSE RESULT:")
print("=" * 60)

result = parse_message(test_message)
print(f"\nSuccess: {result.success}")
print(f"Error: {result.error_message}")
print(f"Number of trades parsed: {len(result.trades)}")

for i, trade in enumerate(result.trades, 1):
    print(f"\n--- Trade {i} ---")
    print(f"  Trade type: {trade.trade_type}")
    print(f"  Contract: {trade.contract_address}")
    print(f"  Chain: {trade.chain}")
    print(f"  Amount spent: {trade.amount_spent}")
    print(f"  Currency: {trade.spend_currency}")
    print(f"  Market cap: {trade.market_cap}")
    print(f"  Notes URL: {trade.notes_url}")
    print(f"  Confidence: {trade.parse_confidence}")
    print(f"  Missing fields: {trade.missing_fields}")

print()
print("=" * 60)
print("FORMATTED SUMMARY (what bot would show):")
print("=" * 60)
print(format_parse_summary(result))
