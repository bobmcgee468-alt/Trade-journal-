-- schema.sql - Database structure for the Trade Journal Bot
--
-- WHAT THIS FILE DOES:
-- Defines all the tables (like spreadsheets) where your trade data lives.
-- Each table has columns (fields) with specific types (text, numbers, dates).
--
-- LEARNING MOMENT: Relational Databases
-- Tables can reference each other using "foreign keys". For example, a trade
-- references a token_id, which points to a row in the tokens table. This means
-- you store the token info once, not repeated in every trade.
--
-- HOW TO READ THIS:
-- - CREATE TABLE: Makes a new table
-- - Column definitions: name TYPE constraints
-- - PRIMARY KEY: Unique identifier for each row
-- - REFERENCES: Links to another table (foreign key)
-- - DEFAULT: Value used if you don't specify one

-- Enable foreign key enforcement (SQLite needs this explicitly)
PRAGMA foreign_keys = ON;

-- ============================================================================
-- WALLETS TABLE
-- ============================================================================
-- Tracks which wallets you trade from.
-- Why separate? You might trade from multiple wallets and want to analyze by wallet.

CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Auto-generated unique ID
    address TEXT NOT NULL,                  -- Wallet address (0x... or Solana format)
    chain TEXT NOT NULL,                    -- 'ethereum', 'solana', 'base', 'bsc', etc.
    nickname TEXT,                          -- Optional friendly name like "Main Wallet"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure we don't accidentally add the same wallet twice
    UNIQUE(address, chain)
);

-- ============================================================================
-- TOKENS TABLE
-- ============================================================================
-- Stores token information so we don't refetch it every time.
-- Same token appears in many trades - storing it once avoids duplication.

CREATE TABLE IF NOT EXISTS tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_address TEXT NOT NULL,         -- The token's contract address
    chain TEXT NOT NULL,                    -- Which blockchain
    symbol TEXT,                            -- Ticker like "PEPE" or "WIF"
    name TEXT,                              -- Full name like "Pepe" or "dogwifhat"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Same contract can exist on different chains (though rare)
    UNIQUE(contract_address, chain)
);

-- ============================================================================
-- POSITIONS TABLE
-- ============================================================================
-- Groups related buys and sells together for PnL tracking.
--
-- LEARNING MOMENT: What is a Position?
-- A "position" is your stake in a token. You might:
--   1. Buy $100 of PEPE
--   2. Buy $50 more when it dips
--   3. Sell half your stack
--   4. Sell the rest
-- That's ONE position with FOUR trades. This table tracks the aggregate.

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id INTEGER NOT NULL REFERENCES tokens(id),
    wallet_id INTEGER REFERENCES wallets(id),  -- Optional: which wallet

    -- Status: OPEN (holding), PARTIAL (sold some), CLOSED (fully exited)
    status TEXT DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'PARTIAL', 'CLOSED')),

    -- Aggregated quantities (updated as trades happen)
    total_bought REAL DEFAULT 0,            -- Total tokens ever bought
    total_sold REAL DEFAULT 0,              -- Total tokens ever sold
    remaining_tokens REAL DEFAULT 0,        -- What you still hold

    -- Cost tracking (for PnL calculation)
    total_cost_usd REAL DEFAULT 0,          -- Total USD spent buying
    total_proceeds_usd REAL DEFAULT 0,      -- Total USD received from selling

    -- Profit and Loss
    realized_pnl_usd REAL DEFAULT 0,        -- Profit/loss from sold portions

    -- Timestamps
    opened_at TIMESTAMP,                    -- When first buy happened
    closed_at TIMESTAMP,                    -- When fully sold (if applicable)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- TRADES TABLE
-- ============================================================================
-- Every individual buy or sell you make. This is the main "journal" table.

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- What was traded (links to other tables)
    token_id INTEGER NOT NULL REFERENCES tokens(id),
    wallet_id INTEGER REFERENCES wallets(id),
    position_id INTEGER REFERENCES positions(id),

    -- Trade type: BUY or SELL
    trade_type TEXT NOT NULL CHECK(trade_type IN ('BUY', 'SELL')),

    -- Amounts
    amount_spent REAL,                      -- How much you spent (in spend_currency)
    spend_currency TEXT,                    -- 'USD', 'USDC', 'ETH', 'SOL', etc.
    amount_tokens REAL,                     -- How many tokens bought/sold

    -- Prices at time of trade
    price_usd REAL,                         -- Price per token in USD
    total_value_usd REAL,                   -- Total trade value in USD
    market_cap_at_trade REAL,               -- Market cap when you entered (you track this!)

    -- Metadata
    source_message TEXT,                    -- Original Telegram message (for debugging)
    notes_url TEXT,                         -- Thesis link or notes URL
    dex_screener_url TEXT,                  -- If they sent a DEX Screener link

    -- Timestamps
    trade_timestamp TIMESTAMP,              -- When the trade actually happened
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- When we recorded it
);

-- ============================================================================
-- INDEXES
-- ============================================================================
-- Indexes make lookups faster. Think of them like the index at the back of a book.
-- Without an index, the database has to scan every row. With an index, it can
-- jump directly to matching rows.

-- Find trades for a specific token quickly
CREATE INDEX IF NOT EXISTS idx_trades_token ON trades(token_id);

-- Find trades for a specific position quickly
CREATE INDEX IF NOT EXISTS idx_trades_position ON trades(position_id);

-- Find open positions quickly (most common query)
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);

-- Find tokens by contract address quickly
CREATE INDEX IF NOT EXISTS idx_tokens_contract ON tokens(contract_address, chain);

-- Find positions by token quickly
CREATE INDEX IF NOT EXISTS idx_positions_token ON positions(token_id);
