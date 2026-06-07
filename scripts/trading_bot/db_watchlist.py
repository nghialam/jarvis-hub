"""DB Watchlist Helper - Unified database interface for Jarvis Hub watchlists.

Central module that provides functions to query the unified jarvis.db 
watchlist_symbols table, replacing the old JSON config-based approach.

Usage:
    from db_watchlist import get_all_symbols, get_symbol_by_id
    
    symbols = get_all_symbols()   # Returns list of symbol dicts
    vci = get_symbol("VCI")       # Returns single symbol dict or None
"""
import sqlite3
import json
import os
from datetime import datetime

# jarvis.db thực tế nằm ở /Users/nghialam/jarvis-hub/knowledge/jarvis.db
# Không dùng __file__ vì trading_bot/knowledge/ không tồn tại
DB_PATH = "/Users/nghialam/jarvis-hub/knowledge/jarvis.db"


def _get_connection():
    """Get a SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_symbols(asset_type=None):
    """Fetch all watchlist symbols from unified DB.
    
    Args:
        asset_type: Optional filter ('VN_STOCK', 'US_EQUITY', 'CRYPTO', 'ETF')
    
    Returns:
        list of dicts with keys: id, symbol, name, asset_type, sector, board, etc.
    """
    conn = _get_connection()
    try:
        if asset_type:
            cursor = conn.execute(
                "SELECT * FROM watchlist_symbols WHERE asset_type=? ORDER BY symbol",
                (asset_type,)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM watchlist_symbols ORDER BY asset_type, symbol"
            )
        rows = [dict(row) for row in cursor.fetchall()]
        return rows
    finally:
        conn.close()


def get_symbol(symbol):
    """Fetch a single symbol's data from the DB.
    
    Args:
        symbol: Ticker string (e.g., 'VCI', 'AAPL')
    
    Returns:
        dict with symbol data or None if not found
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM watchlist_symbols WHERE symbol=?", 
            (symbol.upper().strip(),)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_symbol(symbol, name="", asset_type="VN_STOCK", sector="", industry="", board=""):
    """Insert or update a symbol in the watchlist DB.
    
    Returns:
        True if successful, False on error
    """
    conn = _get_connection()
    try:
        # Check if exists
        cursor = conn.execute(
            "SELECT id FROM watchlist_symbols WHERE symbol=?",
            (symbol.upper().strip(),)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Update existing
            conn.execute("""
                UPDATE watchlist_symbols 
                SET name=?, asset_type=?, sector=?, industry=?, board=?, updated_at=CURRENT_TIMESTAMP
                WHERE symbol=?
            """, (name, asset_type, sector, industry, board, symbol.upper().strip()))
        else:
            # Insert new
            conn.execute("""
                INSERT INTO watchlist_symbols 
                 (symbol, name, asset_type, sector, industry, board)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (symbol.upper().strip(), name, asset_type, sector, industry, board))
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[DB_WATCHLIST] Error adding/updating symbol {symbol}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def remove_symbol(symbol):
    """Remove a symbol from the watchlist DB.
    
    Returns:
        True if removed, False if not found or error
    """
    sym = symbol.upper().strip()
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM watchlist_symbols WHERE symbol=?", (sym,)
        )
        if cursor.rowcount == 0:
            return False
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[DB_WATCHLIST] Error removing symbol {sym}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def update_symbol_price(symbol, price, change_pct=None, volume=None):
    """Update price data for a symbol. Called by refresh loop."""
    sym = symbol.upper().strip()
    conn = _get_connection()
    try:
        if change_pct is not None and volume is not None:
            conn.execute("""
                UPDATE watchlist_symbols 
                SET last_price=?, change_pct=?, volume=?, updated_at=CURRENT_TIMESTAMP
                WHERE symbol=?
            """, (price, change_pct, volume, sym))
        elif change_pct is not None:
            conn.execute("""
                UPDATE watchlist_symbols 
                SET last_price=?, change_pct=?, updated_at=CURRENT_TIMESTAMP
                WHERE symbol=?
            """, (price, change_pct, sym))
        elif volume is not None:
            conn.execute("""
                UPDATE watchlist_symbols 
                SET last_price=?, volume=?, updated_at=CURRENT_TIMESTAMP
                WHERE symbol=?
            """, (price, volume, sym))
        
        conn.commit()
    except sqlite3.Error as e:
        print(f"[DB_WATCHLIST] Error updating price for {sym}: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_symbols_for_asset_type(asset_type):
    """Get symbols filtered by asset type (VN_STOCK, US_EQUITY, CRYPTO, ETF)."""
    return [row["symbol"] for row in get_all_symbols(asset_type)]


# CLI test entry point
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        assets = ["VN_STOCK", "US_EQUITY", "CRYPTO", "ETF"]
        for atype in assets:
            syms = get_all_symbols(atype)
            print(f"\n[{atype}] {len(syms)} symbols:")
            for sym in syms:
                name_str = f" ({sym['name']})" if sym.get("name") else ""
                print(f"   - {sym['symbol']}{name_str}: ${sym.get('last_price', 'N/A')}")
    
    elif len(sys.argv) > 2 and sys.argv[1] == "add":
        symbol = sys.argv[2]
        name = sys.argv[3] if len(sys.argv) > 3 else ""
        asset = sys.argv[4] if len(sys.argv) > 4 else "VN_STOCK"
        result = add_symbol(symbol, name, asset)
        print(f"Added {symbol}: {'OK' if result else 'FAILED'}")
    
    elif len(sys.argv) > 2 and sys.argv[1] == "remove":
        symbol = sys.argv[2]
        result = remove_symbol(symbol)
        print(f"Removed {symbol}: {'OK' if result else 'FAILED'}")
    
    else:
        print("DB Watchlist Helper")
        print("Usage:")
        print("  python db_watchlist.py list               # List all symbols grouped by type")
        print("  python db_watchlist.py add <SYM> [name] [type]")
        print("  python db_watchlist.py remove <SYM>")
