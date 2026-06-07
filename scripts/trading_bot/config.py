#!/usr/bin/env python3
"""
JARVIS Trading Signal Engine - Configuration Module
Tất cả constants, thresholds và connection settings.
"""

# ═══════════════════╗
# Telegram Configuration (Giống Jarvis Intelligence)
# ╔╝
BOT_TOKEN = "8733142640:AAHs32LJp2bdJhbjYlVCaOYWwMl0ERZ0rQk"
TELEGRAM_CHAT_ID = "-1003801745265"     # Gotham News channel

# ═══════════════════╗
# File Paths (relative to trading_bot/)
# ╔╝
BASE_DIR = "/Users/nghialam/jarvis-hub/scripts/trading_bot"
WATCHLIST_FILE = f"{BASE_DIR}/watchlist.json"
SIGNAL_HISTORY_FILE = f"{BASE_DIR}/signal_history.json"

# ═══════════════════╗
# Trading Schedule (Giờ VN)
# ╔╝
TRADING_HOURS_OPEN = 8        # 08:00
TRADING_HOURS_CLOSE = 14.5    # 14:30 (14 + 30/60)

# ═══════════════════╗
# Scanner Configuration
# ╔╝
SCANNER_INTERVAL = 300      # 5 minutes (giây)
MAX_RETRIES = 2             # Retry API calls khi lỗi
API_DELAY = 0.5             # Giây giữa các request VNStock

# ═══════════════════╗
# Technical Indicator Thresholds
# ╔╝

# RSI (Relative Strength Index) - adjusted from default for VN market volatility
RSI_PERIOD = 14
RSI_OVERBOUGHT = 68     # > 68 = overbought -> Sell signal
RSI_OVERSOLD = 32       # < 32 = oversold -> Buy signal

# MACD (Moving Average Convergence Divergence)
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Moving Averages - candle timeframes for cross detection
MA_SHORT = 5            # Short-term MA (5 periods)
MA_LONG = 20            # Long-term MA (20 periods)

# Volume - multiple of average to trigger spike detection
VOLUME_AVERAGE_DAYS = 10
VOLUME_RATIO_THRESHOLD = 1.8     # > 1.8x avg volume = significant spike

# ATR (Average True Range) for stop loss & position sizing
ATR_PERIOD = 14
ATR_MULTIPLIER = 2               # Stop loss = Entry ± (ATR * 2)

# ═══════════════════╗
# Risk Management Limits
# ╔╝
MAX_STOCKS_IN_WATCHLIST = 30    # Maximum symbols in watchlist
MAX_SIGNALS_PER_SCAN = 5        # Max signals per scan to avoid notification spam
MAX_POSITIONS_PER_STOCK = 1     # No duplicate positions on same stock
MIN_CONFIDENCE_THRESHOLD = 30    # Minimum signal confidence (%) to detect signals
                                  # Lowered from 45 (2026-06-05): caught more real signals in ranging markets

# ═══════════════════╗
# Learning Engine
# ╔╝
LEARNING_EVALUATION_WINDOW_DAYS = 7
LEARNING_RETRAIN_INTERVAL_HOURS = 24

# ═══════════════════╗
# Pocket Pivot Detection (Minervini breakout pattern)
PIVOT_LOOKBACK = 40       # Look back ~2 months (40 trading days) for pivot detection

# vnstock API specifics
# ╔╝
VNSTOCK_PAGE_SIZE = 1000       # Max ticks per request
VNSTOCK_MAX_PAGES = 5          # Fetch up to 5 pages for historical data (>=30 candles)

# ═══════════════════╗
# Output Formatting
# ╔╝
SIGNAL_EMOJIS = {
       "BUY": "🟢",
       "SELL": "🔴", 
       "HOLD": "⚪"
}
