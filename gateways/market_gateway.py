"""
gateways/market_gateway.py - Market Data Gateway (Phase 3.13)

JH3.0: Unified interface to all market data sources with automatic fallback.
Sources: vnstock4 → Yahoo Finance → CafeF → Local cache
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from core.config import load_config
from core.db import Database

log = logging.getLogger(__name__)


class MarketGateway:
    """
    Unified market data gateway with automatic source fallback.
    
    Usage:
        gateway = MarketGateway(config, db)
        price = gateway.get_price("VCB", days=30)
        indices = gateway.get_indices(["^VNINDEX.VN", "^HNXINDEX"])
        sector = gateway.get_sector_performance()
    """
    
    def __init__(self, config=None, db=None):
        self.config = config or load_config()
        self.db = db or Database()
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        
    def get_price(self, symbol: str, days: int = 30) -> Dict:
        """
        Get latest price for a stock.
        
        Fallback chain: vnstock4 → Yahoo Finance → CafeF → Local cache
        """
        cache_key = f"price:{symbol}:{days}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Try vnstock4
        price = self._fetch_vnstock4(symbol)
        if price:
            self._cache_result(cache_key, price)
            return price
        
        # Try Yahoo Finance fallback
        price = self._fetch_yahoo_finance(symbol)
        if price:
            self._cache_result(cache_key, price)
            return price
        
        # Try CafeF fallback
        price = self._fetch_cafef(symbol)
        if price:
            self._cache_result(cache_key, price)
            return price
        
        # Last resort: local cache
        price = self._fetch_local_cache(symbol)
        if price:
            return price
        
        log.warning("No price data available for %s", symbol)
        return {"symbol": symbol, "price": None, "source": "none"}
    
    def get_ohlcv(self, symbol: str, period: str = "week", days: int = 90) -> List[Dict]:
        """
        Get OHLCV data for a stock.
        
        Args:
            symbol: Stock symbol
            period: "day", "week", "month"
            days: Number of days of data to retrieve
        """
        cache_key = f"ohlcv:{symbol}:{period}:{days}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Try vnstock4
        data = self._fetch_vnstock4_ohlcv(symbol, period, days)
        if data:
            self._cache_result(cache_key, data)
            return data
        
        # Try Yahoo Finance
        data = self._fetch_yahoo_ohlcv(symbol, period, days)
        if data:
            self._cache_result(cache_key, data)
            return data
        
        log.warning("No OHLCV data available for %s", symbol)
        return []
    
    def get_indices(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        """
        Get market indices data.
        
        Args:
            symbols: List of index symbols (default: VNINDEX, HNXINDEX, UPCOM)
        """
        symbols = symbols or ["^VNINDEX.VN", "^HNXINDEX", ".UPCOM"]
        cache_key = f"indices:{','.join(symbols)}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Try Yahoo Finance
        indices = self._fetch_yahoo_indices(symbols)
        if indices:
            self._cache_result(cache_key, indices)
            return indices
        
        # Try vnstock4
        indices = self._fetch_vnstock4_indices(symbols)
        if indices:
            self._cache_result(cache_key, indices)
            return indices
        
        log.warning("No index data available")
        return []
    
    def get_sector_performance(self) -> List[Dict]:
        """
        Get sector performance data.
        """
        cache_key = "sector_performance"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Try vnstock4
        data = self._fetch_vnstock4_sectors()
        if data:
            self._cache_result(cache_key, data)
            return data
        
        # Try database
        data = self._fetch_db_sectors()
        if data:
            return data
        
        return []
    
    def get_crypto(self, symbol: str = "BTC") -> Dict:
        """
        Get cryptocurrency price.
        """
        cache_key = f"crypto:{symbol}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Try Yahoo Finance
        data = self._fetch_yahoo_crypto(symbol)
        if data:
            self._cache_result(cache_key, data)
            return data
        
        log.warning("No crypto data available for %s", symbol)
        return {"symbol": symbol, "price": None, "source": "none"}
    
    def get_exchange_rates(self) -> List[Dict]:
        """
        Get exchange rates (USD, SGD, JPY, EUR, GBP).
        """
        cache_key = "exchange_rates"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Try Yahoo Finance
        data = self._fetch_yahoo_fx()
        if data:
            self._cache_result(cache_key, data)
            return data
        
        # Try vnstock4
        data = self._fetch_vnstock4_fx()
        if data:
            self._cache_result(cache_key, data)
            return data
        
        return []
    
    def get_technical_indicators(self, symbol: str, days: int = 90) -> Dict:
        """
        Calculate technical indicators for a stock.
        
        Returns: RSI, MACD, Bollinger Bands, MA, EMA, etc.
        """
        cache_key = f"indicators:{symbol}:{days}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Get OHLCV data
        ohlcv = self.get_ohlcv(symbol, period="day", days=days)
        if not ohlcv:
            return {"symbol": symbol, "indicators": {}}
        
        # Calculate indicators
        indicators = self._calculate_indicators(ohlcv)
        self._cache_result(cache_key, indicators)
        return indicators
    
    def refresh_all(self):
        """
        Refresh all market data and cache.
        """
        log.info("Refreshing all market data...")
        symbols = ["^VNINDEX.VN", "^HNKEY.VN", "^VN30", "^HNX30"]
        self.get_indices(symbols)
        self.get_sector_performance()
        self.get_exchange_rates()
        self.get_crypto("BTC")
        log.info("Market data refresh complete")
    
    # --- Private fetch methods ---
    
    def _fetch_vnstock4(self, symbol: str) -> Optional[Dict]:
        """Fetch price from vnstock4."""
        try:
            from vnstock import Market
            mkt = Market()
            data = mkt.equity(symbol).ohlcv(limit=1)
            if data and not data.empty:
                last = data.iloc[-1]
                return {
                    "symbol": symbol,
                    "price": float(last.get("close", last.get("Price", 0))),
                    "volume": int(last.get("Volume", 0)),
                    "source": "vnstock4",
                    "timestamp": datetime.utcnow().isoformat()
                }
        except ImportError:
            log.debug("vnstock4 not available")
        except Exception as e:
            log.error("vnstock4 price fetch failed for %s: %s", symbol, e)
        return None
    
    def _fetch_vnstock4_ohlcv(self, symbol: str, period: str, days: int) -> Optional[List[Dict]]:
        """Fetch OHLCV from vnstock4."""
        try:
            from vnstock import Market
            mkt = Market()
            data = mkt.equity(symbol).ohlcv(
                start=(datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d"),
                end=datetime.utcnow().strftime("%Y-%m-%d")
            )
            if data and not data.empty:
                return json.loads(data.to_json(orient="records"))
        except Exception as e:
            log.error("vnstock4 OHLCV fetch failed for %s: %s", symbol, e)
        return None
    
    def _fetch_vnstock4_indices(self, symbols: List[str]) -> List[Dict]:
        """Fetch indices from vnstock4."""
        try:
            from vnstock import Market
            mkt = Market()
            data = mkt.indices()
            if data is not None and not data.empty:
                return json.loads(data.head(10).to_json(orient="records"))
        except Exception as e:
            log.error("vnstock4 indices fetch failed: %s", e)
        return None
    
    def _fetch_vnstock4_sectors(self) -> Optional[List[Dict]]:
        """Fetch sector performance from vnstock4."""
        try:
            from vnstock import Market
            mkt = Market()
            data = mkt.sector_performance()
            if data is not None and not data.empty:
                return json.loads(data.to_json(orient="records"))
        except Exception as e:
            log.error("vnstock4 sector fetch failed: %s", e)
        return None
    
    def _fetch_vnstock4_fx(self) -> Optional[List[Dict]]:
        """Fetch FX rates from vnstock4."""
        try:
            from vnstock import Market
            mkt = Market()
            data = mkt.forex()
            if data is not None and not data.empty:
                return json.loads(data.head(10).to_json(orient="records"))
        except Exception as e:
            log.error("vnstock4 FX fetch failed: %s", e)
        return None
    
    def _fetch_yahoo_finance(self, symbol: str) -> Optional[Dict]:
        """Fetch price from Yahoo Finance."""
        try:
            import requests
            ticker = f"{symbol}.VN"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("chart", {}).get("result", [{}])[0]
                meta = result.get("meta", {})
                return {
                    "symbol": symbol,
                    "price": float(meta.get("regularMarketPrice", 0)),
                    "currency": meta.get("currency", "VND"),
                    "source": "yahoo",
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            log.error("Yahoo Finance price fetch failed for %s: %s", symbol, e)
        return None
    
    def _fetch_yahoo_ohlcv(self, symbol: str, period: str, days: int) -> Optional[List[Dict]]:
        """Fetch OHLCV from Yahoo Finance."""
        try:
            import requests
            ticker = f"{symbol}.VN"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={days}d&interval=1d"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("chart", {}).get("result", [{}])[0]
                timestamps = result.get("timestamp", [])
                quote = result.get("indicators", {}).get("quote", [{}])[0]
                
                records = []
                for i, ts in enumerate(timestamps):
                    records.append({
                        "date": datetime.utcfromtimestamp(ts).isoformat(),
                        "open": float(quote.get("open", [None])[i] or 0),
                        "high": float(quote.get("high", [None])[i] or 0),
                        "low": float(quote.get("low", [None])[i] or 0),
                        "close": float(quote.get("close", [None])[i] or 0),
                        "volume": int(quote.get("volume", [None])[i] or 0),
                    })
                return records
        except Exception as e:
            log.error("Yahoo Finance OHLCV fetch failed for %s: %s", symbol, e)
        return None
    
    def _fetch_yahoo_indices(self, symbols: List[str]) -> List[Dict]:
        """Fetch indices from Yahoo Finance."""
        try:
            import requests
            indices = []
            for symbol in symbols:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("chart", {}).get("result", [{}])[0]
                    meta = result.get("meta", {})
                    indices.append({
                        "symbol": symbol,
                        "price": float(meta.get("regularMarketPrice", 0)),
                        "change": float(meta.get("chartPreviousClose", 0) - meta.get("regularMarketPrice", 0)),
                        "change_percent": float(
                            (meta.get("regularMarketPrice", 0) - meta.get("chartPreviousClose", 0)) 
                            / meta.get("chartPreviousClose", 1) * 100
                        ),
                        "source": "yahoo",
                        "timestamp": datetime.utcnow().isoformat()
                    })
            return indices
        except Exception as e:
            log.error("Yahoo Finance indices fetch failed: %s", e)
        return []
    
    def _fetch_yahoo_crypto(self, symbol: str) -> Optional[Dict]:
        """Fetch crypto from Yahoo Finance."""
        try:
            import requests
            ticker = f"{symbol}-USD"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("chart", {}).get("result", [{}])[0]
                meta = result.get("meta", {})
                return {
                    "symbol": symbol,
                    "price": float(meta.get("regularMarketPrice", 0)),
                    "currency": "USD",
                    "source": "yahoo",
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            log.error("Yahoo Finance crypto fetch failed for %s: %s", symbol, e)
        return None
    
    def _fetch_yahoo_fx(self) -> Optional[List[Dict]]:
        """Fetch FX rates from Yahoo Finance."""
        try:
            import requests
            currencies = ["USDDON=X", "SGDON=X", "JPYDON=X", "EURDON=X", "GBPDON=X"]
            rates = []
            for ticker in currencies:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("chart", {}).get("result", [{}])[0]
                    meta = result.get("meta", {})
                    name = ticker.replace("DON=X", "/VND")
                    rates.append({
                        "symbol": name,
                        "rate": float(meta.get("regularMarketPrice", 0)),
                        "source": "yahoo",
                        "timestamp": datetime.utcnow().isoformat()
                    })
            return rates
        except Exception as e:
            log.error("Yahoo Finance FX fetch failed: %s", e)
        return None
    
    def _fetch_cafef(self, symbol: str) -> Optional[Dict]:
        """Fallback to CafeF scraping."""
        try:
            import requests
            url = f"https://cafef.vn/{symbol}.ctv"
            resp = requests.get(url, timeout=10)
            # Simple parsing - this is a placeholder, actual parsing would be more complex
            if resp.status_code == 200:
                # Extract price from HTML - simplified
                return {
                    "symbol": symbol,
                    "price": 0,  # Placeholder
                    "source": "cafef",
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            log.error("CafeF fetch failed for %s: %s", symbol, e)
        return None
    
    def _fetch_local_cache(self, symbol: str) -> Optional[Dict]:
        """Fetch from local database cache."""
        try:
            conn = self.db.get_connection()
            row = conn.execute(
                "SELECT price, volume, timestamp FROM market_cache WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1",
                (symbol,)
            ).fetchone()
            if row:
                return {
                    "symbol": symbol,
                    "price": float(row[0]) if row[0] else 0,
                    "volume": int(row[1]) if row[1] else 0,
                    "source": "cache",
                    "timestamp": row[2]
                }
        except Exception as e:
            log.error("Local cache fetch failed for %s: %s", symbol, e)
        return None
    
    def _fetch_db_sectors(self) -> List[Dict]:
        """Fetch sector performance from database."""
        try:
            conn = self.db.get_connection()
            rows = conn.execute(
                "SELECT sector, change_percent, volume FROM sector_performance ORDER BY change_percent DESC"
            ).fetchall()
            return [
                {
                    "sector": row[0],
                    "change_percent": float(row[1]) if row[1] else 0,
                    "volume": float(row[2]) if row[2] else 0,
                }
                for row in rows
            ]
        except Exception as e:
            log.error("DB sector fetch failed: %s", e)
        return []
    
    def _calculate_indicators(self, ohlcv: List[Dict]) -> Dict:
        """
        Calculate technical indicators from OHLCV data.
        Uses numpy/pandas for vectorized calculation.
        """
        try:
            import numpy as np
            
            closes = np.array([c["close"] for c in ohlcv if c.get("close")])
            volumes = np.array([c["volume"] for c in ohlcv if c.get("volume")])
            highs = np.array([c["high"] for c in ohlcv if c.get("high")])
            lows = np.array([c["low"] for c in ohlcv if c.get("low")])
            
            if len(closes) < 2:
                return {"symbol": "unknown", "indicators": {}}
            
            # Simple Moving Averages
            sma_20 = np.mean(closes[-20:]) if len(closes) >= 20 else np.mean(closes)
            sma_50 = np.mean(closes[-50:]) if len(closes) >= 50 else np.mean(closes)
            
            # RSI (14-period)
            delta = np.diff(closes)
            gains = np.where(delta > 0, delta, 0)
            losses = np.where(delta < 0, -delta, 0)
            if len(gains) >= 14:
                avg_gain = np.mean(gains[-14:])
                avg_loss = np.mean(losses[-14:])
                rs = avg_gain / avg_loss if avg_loss != 0 else 100
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 50.0
            
            # MACD
            ema_12 = self._ema(closes, 12)
            ema_26 = self._ema(closes, 26)
            macd = ema_12 - ema_26 if ema_12 and ema_26 else 0
            
            # Bollinger Bands
            std_20 = np.std(closes[-20:]) if len(closes) >= 20 else 0
            bb_upper = sma_20 + (2 * std_20)
            bb_lower = sma_20 - (2 * std_20)
            
            # Volume ratio
            avg_vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
            vol_ratio = volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1.0
            
            return {
                "symbol": "unknown",
                "indicators": {
                    "sma_20": float(sma_20),
                    "sma_50": float(sma_50),
                    "rsi_14": float(rsi),
                    "macd": float(macd),
                    "bb_upper": float(bb_upper),
                    "bb_lower": float(bb_lower),
                    "volume_ratio": float(vol_ratio),
                    "trend": "bullish" if sma_20 > sma_50 else "bearish",
                    "price": float(closes[-1]),
                }
            }
        except Exception as e:
            log.error("Technical indicators calculation failed: %s", e)
            return {"symbol": "unknown", "indicators": {}}
    
    @staticmethod
    def _ema(data: np.ndarray, period: int) -> Optional[float]:
        """Calculate Exponential Moving Average."""
        if len(data) < period:
            return None
        multiplier = 2 / (period + 1)
        ema = np.mean(data[-period:])
        for price in data[-period::-1]:
            ema = (price - ema) * multiplier + ema
        return float(ema)
    
    # --- Cache utilities ---
    
    def _get_from_cache(self, key: str) -> Optional[Dict]:
        """Get cached data if still fresh."""
        if key in self._cache:
            cached_time, value = self._cache[key]
            if time.time() - cached_time < self._cache_ttl:
                return value
            del self._cache[key]
        return None
    
    def _cache_result(self, key: str, value: Dict):
        """Cache a result with timestamp."""
        self._cache[key] = (time.time(), value)
    
    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()
