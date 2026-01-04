"""
models.py - Database operations for trades, tokens, positions, and wallets

WHAT THIS FILE DOES:
Provides functions to Create, Read, Update, and Delete (CRUD) records in the database.
Other parts of the app use these functions instead of writing SQL directly.

LEARNING MOMENT: Why Separate Models?
1. Consistency - All database access goes through one place
2. Abstraction - Rest of the app doesn't need to know SQL
3. Safety - We can validate data before inserting
4. Testability - Easy to mock for testing

LEARNING MOMENT: SQL Injection
Never put user input directly into SQL strings! Always use parameterized queries:
  BAD:  f"SELECT * FROM users WHERE name = '{user_input}'"
  GOOD: "SELECT * FROM users WHERE name = ?", (user_input,)
The ? placeholder safely escapes special characters.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import sqlite3

from .connection import get_connection


# =============================================================================
# TOKEN OPERATIONS
# =============================================================================

def get_or_create_token(
    contract_address: str,
    chain: str,
    symbol: Optional[str] = None,
    name: Optional[str] = None
) -> int:
    """
    Get an existing token or create a new one.

    This is the pattern you'll use most: check if something exists,
    create it if not, return the ID either way.

    Args:
        contract_address: The token's contract address
        chain: Which blockchain
        symbol: Token ticker (e.g., "PEPE")
        name: Token full name

    Returns:
        The token's database ID
    """
    with get_connection() as conn:
        # First, try to find existing token
        cursor = conn.execute(
            """
            SELECT id FROM tokens
            WHERE LOWER(contract_address) = LOWER(?) AND chain = ?
            """,
            (contract_address, chain)
        )
        row = cursor.fetchone()

        if row:
            token_id = row['id']
            # Update symbol/name if we have new info
            if symbol or name:
                conn.execute(
                    """
                    UPDATE tokens
                    SET symbol = COALESCE(?, symbol),
                        name = COALESCE(?, name)
                    WHERE id = ?
                    """,
                    (symbol, name, token_id)
                )
                conn.commit()
            return token_id

        # Create new token
        cursor = conn.execute(
            """
            INSERT INTO tokens (contract_address, chain, symbol, name)
            VALUES (?, ?, ?, ?)
            """,
            (contract_address, chain, symbol, name)
        )
        conn.commit()
        return cursor.lastrowid


def get_token_by_id(token_id: int) -> Optional[Dict[str, Any]]:
    """Get a token by its database ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM tokens WHERE id = ?",
            (token_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def find_token_by_symbol(symbol: str) -> List[Dict[str, Any]]:
    """
    Find tokens by symbol (case-insensitive).
    Returns a list because multiple tokens might have the same symbol.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT t.*, p.status as position_status
            FROM tokens t
            LEFT JOIN positions p ON p.token_id = t.id
            WHERE LOWER(t.symbol) = LOWER(?)
            ORDER BY p.status = 'OPEN' DESC, t.created_at DESC
            """,
            (symbol,)
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# WALLET OPERATIONS
# =============================================================================

def get_or_create_wallet(
    address: str,
    chain: str,
    nickname: Optional[str] = None
) -> int:
    """Get an existing wallet or create a new one."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id FROM wallets
            WHERE LOWER(address) = LOWER(?) AND chain = ?
            """,
            (address, chain)
        )
        row = cursor.fetchone()

        if row:
            return row['id']

        cursor = conn.execute(
            """
            INSERT INTO wallets (address, chain, nickname)
            VALUES (?, ?, ?)
            """,
            (address, chain, nickname)
        )
        conn.commit()
        return cursor.lastrowid


def get_all_wallets() -> List[Dict[str, Any]]:
    """Get all wallets."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM wallets ORDER BY created_at")
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# POSITION OPERATIONS
# =============================================================================

def create_position(
    token_id: int,
    wallet_id: Optional[int] = None
) -> int:
    """Create a new position for a token."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO positions (token_id, wallet_id, status, opened_at)
            VALUES (?, ?, 'OPEN', CURRENT_TIMESTAMP)
            """,
            (token_id, wallet_id)
        )
        conn.commit()
        return cursor.lastrowid


def get_open_position(
    token_id: int,
    wallet_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Find an open or partial position for a token.

    Args:
        token_id: The token's database ID
        wallet_id: Optional wallet filter

    Returns:
        Position dict or None
    """
    with get_connection() as conn:
        if wallet_id:
            cursor = conn.execute(
                """
                SELECT * FROM positions
                WHERE token_id = ? AND wallet_id = ? AND status IN ('OPEN', 'PARTIAL')
                ORDER BY opened_at DESC
                LIMIT 1
                """,
                (token_id, wallet_id)
            )
        else:
            cursor = conn.execute(
                """
                SELECT * FROM positions
                WHERE token_id = ? AND status IN ('OPEN', 'PARTIAL')
                ORDER BY opened_at DESC
                LIMIT 1
                """,
                (token_id,)
            )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_open_positions_by_symbol(symbol: str) -> List[Dict[str, Any]]:
    """
    Find open positions by token symbol.
    Used when user sells without providing contract address.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT p.*, t.symbol, t.name, t.contract_address, t.chain
            FROM positions p
            JOIN tokens t ON t.id = p.token_id
            WHERE LOWER(t.symbol) = LOWER(?) AND p.status IN ('OPEN', 'PARTIAL')
            ORDER BY p.opened_at DESC
            """,
            (symbol,)
        )
        return [dict(row) for row in cursor.fetchall()]


def update_position(
    position_id: int,
    total_bought: Optional[float] = None,
    total_sold: Optional[float] = None,
    remaining_tokens: Optional[float] = None,
    total_cost_usd: Optional[float] = None,
    total_proceeds_usd: Optional[float] = None,
    realized_pnl_usd: Optional[float] = None,
    status: Optional[str] = None
) -> None:
    """Update position fields. Only updates fields that are provided."""
    updates = []
    params = []

    if total_bought is not None:
        updates.append("total_bought = ?")
        params.append(total_bought)
    if total_sold is not None:
        updates.append("total_sold = ?")
        params.append(total_sold)
    if remaining_tokens is not None:
        updates.append("remaining_tokens = ?")
        params.append(remaining_tokens)
    if total_cost_usd is not None:
        updates.append("total_cost_usd = ?")
        params.append(total_cost_usd)
    if total_proceeds_usd is not None:
        updates.append("total_proceeds_usd = ?")
        params.append(total_proceeds_usd)
    if realized_pnl_usd is not None:
        updates.append("realized_pnl_usd = ?")
        params.append(realized_pnl_usd)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
        if status == 'CLOSED':
            updates.append("closed_at = CURRENT_TIMESTAMP")

    if not updates:
        return

    params.append(position_id)

    with get_connection() as conn:
        conn.execute(
            f"UPDATE positions SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()


def get_position_by_id(position_id: int) -> Optional[Dict[str, Any]]:
    """Get a position by ID with token info."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT p.*, t.symbol, t.name, t.contract_address, t.chain
            FROM positions p
            JOIN tokens t ON t.id = p.token_id
            WHERE p.id = ?
            """,
            (position_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_open_positions() -> List[Dict[str, Any]]:
    """Get all open/partial positions with token info."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT p.*, t.symbol, t.name, t.contract_address, t.chain
            FROM positions p
            JOIN tokens t ON t.id = p.token_id
            WHERE p.status IN ('OPEN', 'PARTIAL')
            ORDER BY p.opened_at DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# TRADE OPERATIONS
# =============================================================================

def create_trade(
    token_id: int,
    trade_type: str,
    position_id: Optional[int] = None,
    wallet_id: Optional[int] = None,
    amount_spent: Optional[float] = None,
    spend_currency: Optional[str] = None,
    amount_tokens: Optional[float] = None,
    price_usd: Optional[float] = None,
    total_value_usd: Optional[float] = None,
    market_cap_at_trade: Optional[float] = None,
    source_message: Optional[str] = None,
    notes_url: Optional[str] = None,
    dex_screener_url: Optional[str] = None,
    trade_timestamp: Optional[datetime] = None
) -> int:
    """Create a new trade record."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO trades (
                token_id, trade_type, position_id, wallet_id,
                amount_spent, spend_currency, amount_tokens,
                price_usd, total_value_usd, market_cap_at_trade,
                source_message, notes_url, dex_screener_url, trade_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token_id, trade_type, position_id, wallet_id,
                amount_spent, spend_currency, amount_tokens,
                price_usd, total_value_usd, market_cap_at_trade,
                source_message, notes_url, dex_screener_url,
                trade_timestamp or datetime.now()
            )
        )
        conn.commit()
        return cursor.lastrowid


def get_trades_for_position(position_id: int) -> List[Dict[str, Any]]:
    """Get all trades for a position."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM trades
            WHERE position_id = ?
            ORDER BY trade_timestamp
            """,
            (position_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_recent_trades(limit: int = 10) -> List[Dict[str, Any]]:
    """Get most recent trades with token info."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT tr.*, t.symbol, t.name, t.chain
            FROM trades tr
            JOIN tokens t ON t.id = tr.token_id
            ORDER BY tr.created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_all_trades(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get all trades with token and position info for the trade log.

    Returns trades ordered by most recent first.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT tr.*, t.symbol, t.name, t.chain, t.contract_address,
                   p.status as position_status
            FROM trades tr
            JOIN tokens t ON t.id = tr.token_id
            LEFT JOIN positions p ON p.id = tr.position_id
            ORDER BY tr.trade_timestamp DESC
            LIMIT ?
            """,
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_all_trades_for_year(year: int) -> List[Dict[str, Any]]:
    """Get all trades for a specific year (for year-end review)."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT tr.*, t.symbol, t.name, t.contract_address, t.chain,
                   p.realized_pnl_usd as position_pnl
            FROM trades tr
            JOIN tokens t ON t.id = tr.token_id
            LEFT JOIN positions p ON p.id = tr.position_id
            WHERE strftime('%Y', tr.trade_timestamp) = ?
            ORDER BY tr.trade_timestamp
            """,
            (str(year),)
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# STATISTICS
# =============================================================================

def get_trading_stats() -> Dict[str, Any]:
    """Get overall trading statistics."""
    with get_connection() as conn:
        # Total trades
        total_trades = conn.execute(
            "SELECT COUNT(*) as count FROM trades"
        ).fetchone()['count']

        # Total positions
        total_positions = conn.execute(
            "SELECT COUNT(*) as count FROM positions"
        ).fetchone()['count']

        # Open positions
        open_positions = conn.execute(
            "SELECT COUNT(*) as count FROM positions WHERE status IN ('OPEN', 'PARTIAL')"
        ).fetchone()['count']

        # Total realized PnL
        total_pnl = conn.execute(
            "SELECT COALESCE(SUM(realized_pnl_usd), 0) as total FROM positions"
        ).fetchone()['total']

        # Total invested (sum of all buys)
        total_invested = conn.execute(
            """
            SELECT COALESCE(SUM(total_value_usd), 0) as total
            FROM trades WHERE trade_type = 'BUY'
            """
        ).fetchone()['total']

        return {
            'total_trades': total_trades,
            'total_positions': total_positions,
            'open_positions': open_positions,
            'realized_pnl_usd': total_pnl,
            'total_invested_usd': total_invested
        }
