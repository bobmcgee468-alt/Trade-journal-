"""
connection.py - Database connection management

WHAT THIS FILE DOES:
Provides a simple way to connect to the SQLite database and ensures the
schema (tables) exists. Other files import get_connection() from here.

LEARNING MOMENT: SQLite
SQLite is a "serverless" database - it's just a file on your computer.
No need to install or run a separate database program. The entire database
lives in one file (trades.db). This makes it perfect for small projects.

The trade-off: Only one program can write at a time. For a personal trade
journal, this is fine. For a website with 1000 users, you'd need PostgreSQL.

LEARNING MOMENT: Context Managers (the 'with' statement)
When you see 'with get_connection() as conn:', Python automatically:
1. Opens the connection
2. Runs your code
3. Closes the connection (even if there's an error)
This prevents "connection leaks" where you forget to close connections.
"""

import sqlite3
from pathlib import Path

# Import the database path from config
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    """
    Get a connection to the SQLite database.
    Creates the database file if it doesn't exist.

    Returns:
        sqlite3.Connection: A connection object you can use to query the database

    Example:
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM trades")
            trades = cursor.fetchall()
    """
    # Connect to the database (creates file if it doesn't exist)
    conn = sqlite3.connect(DATABASE_PATH)

    # Return rows as dictionaries instead of tuples
    # This lets you access columns by name: row['symbol'] instead of row[0]
    conn.row_factory = sqlite3.Row

    # Enable foreign key enforcement
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_database():
    """
    Initialize the database by running the schema.sql file.
    Creates all tables if they don't exist.

    Call this once when the bot starts to ensure tables exist.
    """
    # Find the schema.sql file (same directory as this file)
    schema_path = Path(__file__).parent / "schema.sql"

    # Read the SQL commands
    with open(schema_path, "r") as f:
        schema_sql = f.read()

    # Execute all the CREATE TABLE statements
    with get_connection() as conn:
        conn.executescript(schema_sql)
        conn.commit()

    print(f"Database initialized at: {DATABASE_PATH}")


# This runs only when you execute this file directly (not when imported)
# Useful for testing: python database/connection.py
if __name__ == "__main__":
    init_database()
    print("Database setup complete!")

    # Show what tables were created
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row['name'] for row in cursor.fetchall()]
        print(f"Tables created: {tables}")
