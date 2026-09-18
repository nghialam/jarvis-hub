"""
Semantic layer: Unified query abstraction via Python functions + SQLite views.
Precompute daily technical indicators: MA5/10/20/50/200, RSI14, volume ratio, sector ranking.
"""

import sqlite3
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class MarketView:
    """SQLite view for precomputed technical indicators on price data.
    
    Creates/updates views that compute MA/RSI/vol_ratio on-the-fly from daily OHLCV.
    Lightweight: no Cube.js server, pure Python + SQLite.
    """

    CREATE_VIEW_SQL = """
    CREATE VIEW IF NOT EXISTS v_market_indicators AS
    SELECT
        t.date,
        t.symbol,
        t.open,
        t.high,
        t.low,
        t.close,
        t.volume,
        t.adj_close,
        -- Moving averages
        AVG(t2.close) OVER (
            PARTITION BY t.symbol ORDER BY t.date
            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
        ) AS ma5,
        AVG(t2.close) OVER (
            PARTITION BY t.symbol ORDER BY t.date
            ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
        ) AS ma10,
        AVG(t2.close) OVER (
            PARTITION BY t.symbol ORDER BY t.date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS ma20,
        AVG(t2.close) OVER (
            PARTITION BY t.symbol ORDER BY t.date
            ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
        ) AS ma50,
        AVG(t2.close) OVER (
            PARTITION BY t.symbol ORDER BY t.date
            ROWS BETWEEN 199 PRECEDING AND CURRENT ROW
        ) AS ma200,
        -- Volume ratio (current vs 10-day avg)
        t.volume * 1.0 / NULLIF(
            AVG(t2.volume) OVER (
                PARTITION BY t.symbol ORDER BY t.date
                ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
            ), 0
        ) AS volume_ratio
    FROM stock_data t
    INNER JOIN stock_data t2
        ON t2.symbol = t.symbol AND t2.date <= t.date
    GROUP BY t.date, t.symbol
    ORDER BY t.symbol, t.date;
    """

    CREATE_RSI_SQL = """
    CREATE VIEW IF NOT EXISTS v_market_rsi AS
    WITH price_changes AS (
        SELECT
            symbol,
            date,
            close,
            close - LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS price_change
        FROM stock_data
    ),
    gains_losses AS (
        SELECT
            symbol,
            date,
            close,
            price_change,
            CASE WHEN price_change > 0 THEN price_change ELSE 0 END AS gain,
            CASE WHEN price_change < 0 THEN ABS(price_change) ELSE 0 END AS loss
        FROM price_changes
    ),
    avg_gain_loss AS (
        SELECT
            symbol,
            date,
            close,
            -- SMA of gains/losses over 14 periods
            AVG(gain) OVER (PARTITION BY symbol ORDER BY date
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_gain,
            AVG(loss) OVER (PARTITION BY symbol ORDER BY date
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_loss
        FROM gains_losses
    )
    SELECT
        symbol,
        date,
        close,
        avg_gain,
        avg_loss,
        CASE
            WHEN avg_loss = 0 OR avg_loss IS NULL THEN 100.0
            ELSE 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        END AS rsi14
    FROM avg_gain_loss;
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def init_db(self) -> None:
        """Create semantic views in the database."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(self.CREATE_VIEW_SQL)
            conn.executescript(self.CREATE_RSI_SQL)
            conn.commit()
        finally:
            conn.close()

    def get_indicators(self, symbol: str, date_from: str, date_to: Optional[str] = None,
                       limit: Optional[int] = None) -> List[Dict]:
        """Get technical indicators for a symbol."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            where = "WHERE symbol = ? AND date >= ?"
            params: list = [symbol, date_from]

            if date_to:
                where += " AND date <= ?"
                params.append(date_to)

            sql = f"""
            SELECT date, symbol, open, high, low, close, volume, adj_close,
                   ROUND(ma5, 2), ROUND(ma10, 2), ROUND(ma20, 2),
                   ROUND(ma50, 2), ROUND(ma200, 2),
                   ROUND(volume_ratio, 3)
            FROM v_market_indicators
            {where}
            ORDER BY date DESC
            """
            if limit:
                sql += " LIMIT ?"
                params.append(limit)

            rows = cursor.execute(sql, params).fetchall()
            cols = ["date", "symbol", "open", "high", "low", "close", "volume",
                    "adj_close", "ma5", "ma10", "ma20", "ma50", "ma200", "volume_ratio"]
            return [dict(zip(cols, row)) for row in rows]
        finally:
            conn.close()

    def get_rsi(self, symbol: str, date_from: str, date_to: Optional[str] = None,
                limit: Optional[int] = None) -> List[Dict]:
        """Get RSI values for a symbol."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            where = "WHERE symbol = ? AND date >= ?"
            params: list = [symbol, date_from]

            if date_to:
                where += " AND date <= ?"
                params.append(date_to)

            sql = f"""
            SELECT date, symbol, close, rsi14
            FROM v_market_rsi
            {where}
            ORDER BY date DESC
            """
            if limit:
                sql += " LIMIT ?"
                params.append(limit)

            rows = cursor.execute(sql, params).fetchall()
            cols = ["date", "symbol", "close", "rsi14"]
            return [dict(zip(cols, row)) for row in rows]
        finally:
            conn.close()

    def get_latest_for_symbols(self, symbols: List[str]) -> List[Dict]:
        """Get latest indicator values for multiple symbols (snapshot API)."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(symbols))
            sql = f"""
            WITH ranked AS (
                SELECT *,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
                FROM v_market_indicators
                WHERE symbol IN ({placeholders})
            )
            SELECT date, symbol, close, ma5, ma10, ma20, ma50, ma200, volume_ratio
            FROM ranked
            WHERE rn = 1
            ORDER BY symbol
            """
            rows = cursor.execute(sql, symbols).fetchall()
            cols = ["date", "symbol", "close", "ma5", "ma10", "ma20", "ma50", "ma200", "volume_ratio"]
            return [dict(zip(cols, row)) for row in rows]
        finally:
            conn.close()


class AggregateCache:
    """Manages precomputed aggregate data for quick dashboard queries.
    
    Precomputes daily:
    - Sector rankings by volume/gain/loss
    - Market breadth (advancers/decliners)
    - Top movers by % change
    
    Cache is invalidated on new data ingestion via Event system.
    """

    # Tables for aggregated data
    CREATE_TABLES_SQL = """
    CREATE TABLE IF NOT EXISTS aggregate_cache (
        key TEXT NOT NULL PRIMARY KEY,
        value TEXT NOT NULL,
        computed_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS market_breadth (
        date DATE NOT NULL,
        symbol TEXT NOT NULL,
        close REAL,
        prev_close REAL,
        pct_change REAL,
        volume REAL,
        classification TEXT,
        category TEXT
    );
    
    CREATE INDEX IF NOT EXISTS idx_breadth_date ON market_breadth(date);
    CREATE INDEX IF NOT EXISTS idx_breadth_symbol ON market_breadth(symbol);
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def init_db(self) -> None:
        """Create aggregate tables."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(self.CREATE_TABLES_SQL)
            conn.commit()
        finally:
            conn.close()

    def get_cached(self, key: str) -> Optional[Dict]:
        """Get cached result by key."""
        import json
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT value, computed_at FROM aggregate_cache WHERE key = ? AND expires_at > datetime('now')",
                (key,)
            ).fetchone()
            if row:
                return json.loads(row[0])
            return None
        finally:
            conn.close()

    def set_cached(self, key: str, value: Dict, ttl_hours: int = 12) -> None:
        """Cache a result with TTL."""
        import json
        now = datetime.now()
        expires = now.replace(hour=(now.hour + ttl_hours) % 24)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO aggregate_cache (key, value, computed_at, expires_at) VALUES (?, ?, ?, ?)",
                (key, json.dumps(value), now.isoformat(), expires.isoformat())
            )
            conn.commit()
        finally:
            conn.close()

    def invalidate(self, key: str) -> None:
        """Remove cached entry."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM aggregate_cache WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()

    def refresh_all(self) -> Dict:
        """Run full precompute for today. Called by precompute_scheduler."""
        from datetime import date, timedelta
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        results = {}

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # 1. Market breadth
            cursor.execute("""
                INSERT OR REPLACE INTO market_breadth
                SELECT d.date, d.symbol, d.close, p.close,
                       (d.close - p.close) / p.close * 100,
                       d.volume, s.classification, s.category
                FROM stock_data d
                JOIN stock_data p ON d.symbol = p.symbol AND p.date = ?
                JOIN (SELECT DISTINCT symbol, classification, category FROM stock_meta) s
                    ON d.symbol = s.symbol
                WHERE d.date = ?
            """, (yesterday, today))

            # 2. Top gainers/losers
            for label, order in [("gainers", "DESC"), ("losers", "ASC")]:
                cached_key = f"top_{label}_{today}"
                rows = cursor.execute("""
                    SELECT symbol, close, volume, pct_change
                    FROM market_breadth
                    WHERE date = ?
                    ORDER BY pct_change {order}
                    LIMIT 10
                """.format(order=order), (today,)).fetchall()
                results[label] = rows
                self.set_cached(cached_key, {"rows": rows, "date": today})

            # 3. Sector volume ranking
            cached_key = f"sector_rank_{today}"
            rows = cursor.execute("""
                SELECT classification, SUM(volume) as total_vol, COUNT(*) as count
                FROM market_breadth
                WHERE date = ?
                GROUP BY classification
                ORDER BY total_vol DESC
            """, (today,)).fetchall()
            results["sector_rank"] = rows
            self.set_cached(cached_key, {"rows": rows, "date": today})

            conn.commit()
        finally:
            conn.close()

        return results

    def get_market_breadth(self, date: str) -> List[Dict]:
        """Get market breadth for a given date."""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM market_breadth WHERE date = ? ORDER BY symbol",
                (date,)
            ).fetchall()
            cols = ["date", "symbol", "close", "prev_close", "pct_change",
                    "volume", "classification", "category"]
            return [dict(zip(cols, row)) for row in rows]
        finally:
            conn.close()
