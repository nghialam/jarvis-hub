#!/usr/bin/env python3
"""jarvis-migrate.py — Unified Jarvis Hub watchlist migration v1.0

Purpose: Migrate existing simple watchlist table + JSON config into a single,
unified database with:
  - Extended watchlist_symbols (sector, board, asset_type, price data, etc.)
  - signals_log table for Telegram/integration delivery tracking  
  - price_history table for technical analysis and charting

Usage:
    cd /Users/nghialam/jarvis-hub && python3 jarvis-migrate.py
"""
import json
import sqlite3
import sys
import os
from datetime import datetime, timezone
from urllib.request import urlopen
from urllib.error import URLError

DB_PATH = os.path.join(os.path.dirname(__file__), "knowledge", "jarvis.db")
JSON_WATCHLIST = os.path.join(
    os.path.dirname(__file__), "scripts", "trading_bot", "watchlist.json"
)

# Asset type detection by prefix convention
ASSET_MAP = {
    "AAPL": "US_EQUITY", "MSFT": "US_EQUITY", "TSLA": "US_EQUITY",
    "AMZN": "US_EQUITY", "GOOGL": "US_EQUITY", "META": "US_EQUITY",
    "NVDA": "US_EQUITY", "BTC": "CRYPTO", "ETH": "CRYPTO",
    "VNM": "ETF",   # VanEck VIE ETF
    "TEST": "ETF",  # YieldMax TSLA ETF
}

# Vietnamese stock sector mapping (approximate, can be auto-fetched from DNSE)
VN_SECTORS = {
    "VCB": ("Banking", "Finance"), "TPB": ("Banking", "Finance"),
    "MBB": ("Banking", "Finance"), "ACB": ("Banking", "Finance"),
    "TCH": ("Banking", "Finance"), "TCB": ("Banking", "Finance"),
    "PDR": ("Real Estate", "Property Development"),
    "NLG": ("Real Estate", "Property Development"),
    "DXG": ("Real Estate", "Property Development"),
    "VHM": ("Real Estate", "Property & Retail"),
    "CTD": ("Real Estate", "Tourism & Real Estate"),
    "VIC": ("Construction", "Cement"),
    "PVS": ("Energy", "Oil & Gas"),
    "FPT": ("Technology", "Software & Services"),
    "VCI": ("Securities", "Financial Services"),
    "FTS": ("Transport", "Sea Transport"),
    "HCM": ("Real Estate", "Property Development"),
    "BMP": ("Insurance", "PBO Insurance"),
    "VGI": ("Conglomerate", "Diversified"),
    "FRT": ("Retail", "Food Retail"),
    "VIX": ("Investment", "Financial Services"),
    "EVF": ("Construction", "Engineering Construction"),
}


def detect_asset_type(symbol: str) -> str:
    """Detect asset type from symbol convention."""
    sym = symbol.upper().strip()
    if sym in ASSET_MAP:
        return ASSET_MAP[sym]
    # VN stocks tend to be 2-4 uppercase letters
    if all(c.isalpha() and c.isupper() for c in sym) and 2 <= len(sym) <= 5:
        return "VN_STOCK"
    return "OTHER"


def detect_sector_board(symbol: str) -> tuple:
    """Return (sector, board) using heuristic mapping."""
    sym = symbol.upper().strip()
    sector_info = VN_SECTORS.get(sym, ("Unknown", "Unknown"))
    # Board detection from watchlist DB if available
    return sector_info[0], sector_info[1]


def fetch_symbol_info_from_api(symbol: str):
    """Attempt to enrich symbol data via DNSE security definition.
    
    Returns dict with sector, board, industry, name or None.
    """
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "dnse_sdk"))
        from dnse_provider import API_KEY, API_SECRET
        from dnse.api.client import DNSEClient

        client = DNSEClient(api_key=API_KEY, api_secret=API_SECRET)
        status, body = client.get_security_definition(symbol.upper())
        if status == 200 and body:
            data = json.loads(body)
            if isinstance(data, list):
                for item in data:
                    if item.get("symbol", "").upper() == symbol.upper():
                        return {
                            "sector": item.get("sectorId", ""),
                            "board": item.get("boardId", ""),
                            "industry": item.get("industryCode", ""),
                            "name": item.get("nameVn", ""),
                            "isin": item.get("isin", ""),
                        }
        elif status == 200 and body:
            data = json.loads(body)
            if isinstance(data, dict):
                fields = ["sectorId", "boardId", "industryCode", "nameVn", "isin"]
                return {k: v for k, v in data.items() if k in fields}
    except Exception as e:
        print(f"[MIGRATE] DNSE lookup failed for {symbol}: {e}")
    return None


class JarvisMigration:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    # ----------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------
    def run_sql(self, sql: str, params=None):
        """Execute SQL with error handling."""
        try:
            if params:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"[MIGRATE] SQL error: {e}")
            print(f"  SQL: {sql[:200]}")
            self.conn.rollback()
            return False

    def table_exists(self, name: str) -> bool:
        """Check if a table exists."""
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        )
        return self.cursor.fetchone() is not None

    # ----------------------------------------------------------------------
    # Migration execution
    # ------------------------------------------------------------------
    def create_new_schema(self):
        """Create unified schema tables."""
        print("[MIGRATE] Creating unified schema...")

         # Extend watchlist table (keep old for safety, drop later if needed)
        result = self.run_sql("""
            CREATE TABLE IF NOT EXISTS watchlist_symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) UNIQUE NOT NULL COLLATE NOCASE,
                name TEXT DEFAULT '',
                asset_type VARCHAR(20) DEFAULT 'VN_STOCK' CHECK(asset_type IN (
                     'VN_STOCK', 'US_EQUITY', 'CRYPTO', 'ETF', 'OTHER')),
                market VARCHAR(50),            -- STO/UPX or EXCHANGE
                board VARCHAR(20),             -- G1, T1, etc.
                sector TEXT,                   -- Sector category
                industry TEXT,                 -- Industry sub-category
                last_price REAL,               -- Latest price (from API)
                change_pct REAL,              -- Change % 
                volume REAL,                  -- Trading volume
                bid1 REAL, ask1 REAL,        -- Best bid/ask
                bid1_vol REAL, ask1_vol REAL,    -- At best level
                metadata TEXT,                -- JSON extra fields (pe_ratio, market_cap etc.)
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
             );
        """)
        
         # Create indexes separately (SQLite doesn't support INLINE index in CREATE TABLE)
        self.run_sql("CREATE INDEX IF NOT EXISTS idx_wls_symbol ON watchlist_symbols(symbol)")

        # Signals log table for alert tracking & delivery
        self.run_sql("""
          CREATE TABLE IF NOT EXISTS signals_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              symbol VARCHAR(20) NOT NULL,
              asset_type VARCHAR(20),
              signal_type VARCHAR(50) NOT NULL,   -- BUY/SELL/HOLD/STOP_LOSS/etc.
              strength REAL DEFAULT 0 CHECK(strength >= 0 AND strength <= 100),
              price REAL,                      -- Price at signal time
              details TEXT,                    -- JSON: reason, indicators, recommendations
                
              detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              delivered BOOLEAN DEFAULT FALSE,
              delivery_channel VARCHAR(50)    -- telegram:gotham / telegram:private
          );
        """)
        
        # Create indexes for signals_log separately
        self.run_sql("CREATE INDEX IF NOT EXISTS idx_sl_symbol_time ON signals_log(symbol, detected_at)")

        # Price history for charting and technical analysis
        self.run_sql("""
          CREATE TABLE IF NOT EXISTS price_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              symbol VARCHAR(20) NOT NULL,
              date DATE NOT NULL,
              open REAL, high REAL, low REAL, close REAL, volume REAL,
              timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(symbol, date)
          );
        """)
        
        # Create index for price_history separately
        self.run_sql("CREATE INDEX IF NOT EXISTS idx_ph_symbol_date ON price_history(symbol, date DESC)")

        print("[MIGRATE] ✓ Schema created successfully.")

    def migrate_watchlist_data(self):
        """Migrate existing watchlist + JSON config into unified system."""
        print("\n[MIGRATE] Migrating watchlist data...")
        
        # Collect symbols from both sources
        json_symbols = self._load_json_symbols()
        db_symbols = self._load_db_symbols()

        all_symbols = list(dict.fromkeys(json_symbols + db_symbols))  # dedupe, preserve order
        print(f"  Found {len(all_symbols)} unique symbols")

        for sym in all_symbols:
            sym_upper = sym.upper().strip()
            
             # Skip non-standard symbols (numbers, mixed case that aren't real)
            if not all(c.isalpha() and c.isupper() for c in sym_upper):
                print(f"  SKIP {sym_upper}: not a valid ticker")
                continue

            # Check if already exists
            self.cursor.execute("SELECT id FROM watchlist_symbols WHERE symbol=?", (sym_upper,))
            existing = self.cursor.fetchone()
            
            # Try to enrich with DNSE data first
            api_info = fetch_symbol_info_from_api(sym_upper)
            sector_name, board_name = detect_sector_board(sym_upper)

            asset_type = detect_asset_type(sym_upper)

            if existing is None:
                # Insert new symbol
                metadata_json = json.dumps(api_info) if api_info else "{}"
                
                name = (api_info.get("name") if api_info else "") or ""
                if not name and existing:
                    name = existing["name"] or ""

                result = self.run_sql("""
                    INSERT INTO watchlist_symbols 
                    (symbol, name, asset_type, market, board, sector, industry, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (sym_upper, name, asset_type, None, board_name, sector_name, "", metadata_json))

                if result:
                    print(f"  ✓ Added {sym_upper} ({asset_type}, {sector_name} / {board_name or 'N/A'})")
                else:
                    print(f"  ✗ Failed to add {sym_upper}")
            else:
                # Update existing symbol with enriched data if not already present
                if not (api_info.get("sectorId") and api_info.get("sectorId")):
                    self.run_sql("""
                        UPDATE watchlist_symbols 
                        SET sector=?, board=?, industry=?, updated_at=CURRENT_TIMESTAMP,
                            metadata=?
                        WHERE symbol=?
                    """, (
                        api_info.get("sector") or sector_name,
                        api_info.get("board") or board_name,
                        api_info.get("industry") or "",
                        json.dumps(api_info) if api_info else "{}",
                        sym_upper
                    ))
                    print(f"  ~ Updated {sym_upper} with enriched data")

    def _load_json_symbols(self):
        """Load symbols from watchlist.json."""
        if not os.path.exists(JSON_WATCHLIST):
            print(f"[MIGRATE] JSON file not found: {JSON_WATCHLIST}")
            return []
        
        try:
            with open(JSON_WATCHLIST) as f:
                data = json.load(f)
            return [s.upper().strip() for s in data.get("stocks", []) if s]
        except Exception as e:
            print(f"[MIGRATE] Error reading JSON watchlist: {e}")
            return []

    def _load_db_symbols(self):
        """Load symbols from existing watchlist table."""
        try:
            self.cursor.execute("SELECT symbol FROM watchlist ORDER BY id")
            rows = self.cursor.fetchall()
            return [row["symbol"].upper().strip() for row in rows]
        except sqlite3.Error as e:
            print(f"[MIGRATE] Error reading DB watchlist: {e}")
            return []

    def migrate_price_history(self):
        """Optional: attempt to backfill price history from existing data."""
        print("\n[MIGRATE] Migrating price history...")
        
        # Check what's in market_cache
        self.cursor.execute("""
            SELECT symbol, data_json FROM market_cache 
            ORDER BY cached_at DESC
            LIMIT 100
        """)
        rows = self.cursor.fetchall()
        
        migrated_count = 0
        for row in rows:
            try:
                data = json.loads(row["data_json"])
                symbol = row["symbol"].upper().strip()
                
                # Check if already in price_history
                self.cursor.execute(
                    "SELECT id FROM price_history WHERE symbol=? AND date=?",
                    (symbol, data.get("date", ""))
                )
                if self.cursor.fetchone():
                    continue
                
                ohlc = {
                    "open": data.get("open") or data.get("Open"),
                    "high": data.get("high") or data.get("High"),
                    "low": data.get("low") or data.get("Low"),
                    "close": data.get("close") or data.get("Close"),
                    "volume": data.get("volume") or data.get("Volume") or 0,
                }
                
                date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
                
                self.run_sql("""
                    INSERT OR IGNORE INTO price_history 
                    (symbol, date, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol, date, ohlc.get("open"), ohlc.get("high"),
                     ohlc.get("low"), ohlc.get("close"), ohlc.get("volume")))
                
                if self.cursor.rowcount > 0:
                    migrated_count += 1
            except Exception as e:
                continue
        
        print(f"  ✓ Migrated {migrated_count} price records")

    def verify_migration(self):
        """Show migration summary."""
        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        
        # Count symbols by asset type
        self.cursor.execute("""
            SELECT asset_type, COUNT(*) as cnt 
            FROM watchlist_symbols GROUP BY asset_type ORDER BY asset_type
        """)
        print("\nSymbols by asset type:")
        for row in self.cursor.fetchall():
            print(f"  {row['asset_type']}: {row['cnt']}")
        
        # Total count
        self.cursor.execute("SELECT COUNT(*) as cnt FROM watchlist_symbols")
        total = self.cursor.fetchone()["cnt"]
        print(f"\n  Total symbols: {total}")
        
        # Show all symbols ordered by type then symbol name
        self.cursor.execute("""
            SELECT symbol, asset_type, sector, board, name 
            FROM watchlist_symbols ORDER BY asset_type, symbol
        """)
        rows = self.cursor.fetchall()
        current_type = None
        for row in rows:
            if row["asset_type"] != current_type:
                current_type = row["asset_type"]
                print(f"\n  [{current_type}]")
            name_str = f" ({row['name']})" if row["name"] else ""
            board_str = f" {row['board']}" if row["board"] else ""
            print(f"    - {row['symbol']}{name_str}{board_str}")
        
        # Price history count
        self.cursor.execute("SELECT COUNT(*) as cnt FROM price_history")
        pcnt = self.cursor.fetchone()["cnt"]
        print(f"\n  Price records: {pcnt}")
        
        # Signals log count (should be 0 initially)
        self.cursor.execute("SELECT COUNT(*) as cnt FROM signals_log")
        scnr = self.cursor.fetchone()["cnt"]
        print(f"  Signal alerts stored: {scnr}")
        
        print("=" * 60)

    def close(self):
        """Close DB connection."""
        if self.conn:
            self.conn.close()


def main():
    """Run full migration."""  
    print("=" * 60)
    print("JARVIS HUB UNIFIED WATCHLIST MIGRATION v1.0")
    print("=" * 60)
    
    print(f"\nDatabase: {DB_PATH}")
    print(f"JSON config: {JSON_WATCHLIST}")
    
    migration = JarvisMigration()
    
    try:
        # Phase 1: Create schema
        migration.create_new_schema()
        
        # Phase 2: Migrate watchlist data  
        migration.migrate_watchlist_data()
        
         # Phase 3: Migrate price history (optional, best-effort)
        migration.migrate_price_history()
        
        # Phase 4: Verification
        migration.verify_migration()
        
        print("\n✅ Migration completed successfully!")
        return 0
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Migration interrupted by user")  
        return 1
    except Exception as e:
        print(f"\n\n❌ Fatal error during migration: {e}")
        import traceback
        traceback.print_exc()
        return 2
    finally:
        migration.close()


if __name__ == "__main__":
    sys.exit(main())
