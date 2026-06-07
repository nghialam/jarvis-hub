#!/usr/bin/env python3
"""Test vnstock4 OHLCV API for jarvis-hub migration."""
import warnings
warnings.filterwarnings('ignore')

from vnstock import Market
import pandas as pd

# Test equity.ohlcv() - daily candles
print("=== MARKET EQUITY OHLCV (VCI daily) ===")
try:
    eq = Market().equity(symbol="VCI")
    df = eq.ohlcv(start="2025-05-01", end="2026-05-31", resolution="1D")
    print(f"Type: {type(df)}")
    if isinstance(df, pd.DataFrame):
        print(f"\nShape: {df.shape}")
        print(f"\nColumns: {list(df.columns)}")
        print("\nLast 5 rows:")
        print(df.tail(5).to_string())
        print(f"\nDate range: {df.index.min()} to {df.index.max()}")
    else:
        print(f"Result type: {type(df)}, content:\n{str(df)[:800]}")
except Exception as e:
    print(f"Error: {e}")
    import traceback; traceback.print_exc()

# Test with 5-minute resolution for intraday
print("\n=== MARKET EQUITY OHLCV (VCI 1min) ===")
try:
    eq = Market().equity(symbol="VCI")
    df = eq.ohlcv(start="2026-05-30", end="2026-05-30", resolution="1M", count=50)
    print(f"Type: {type(df)}")
    if isinstance(df, pd.DataFrame):
        print(f"Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print("\nFirst 5 rows:")
        print(df.head(5).to_string())
        print("Last 5 rows:")
        print(df.tail(5).to_string())
    else:
        print(f"Result type: {type(df)}, content:\n{str(df)[:800]}")
except Exception as e:
    print(f"Error: {e}")
    import traceback; traceback.print_exc()

# Test another symbol (VIC, VCB)
print("\n=== MARKET EQUITY OHLCV (VCB daily) ===")
try:
    eq = Market().equity(symbol="VCB")
    df = eq.ohlcv(start="2026-05-01", end="2026-05-31", resolution="1D", count=30)
    if isinstance(df, pd.DataFrame):
        print(f"Shape: {df.shape}, Columns: {list(df.columns)}")
        print(df.tail(3).to_string())
except Exception as e:
    print(f"Error: {e}")

# Test intraday with 5-min resolution — this is what jarvis-hub main needs
print("\n=== MARKET EQUITY OHLCV (VCI 5min, in-session) ===")
try:
    eq = Market().equity(symbol="VCI")
    df = eq.ohlcv(start="2026-06-01", end="2026-06-01", resolution="5M", count=80)
    if isinstance(df, pd.DataFrame):
        print(f"Shape: {df.shape}, Columns: {list(df.columns)}")
        print("\nFirst 5 rows:")
        print(df.head(5).to_string())
        print("Last 5 rows:")
        print(df.tail(5).to_string())
    else:
        print(f"Result type: {type(df)}, content:\n{str(df)[:800]}")
except Exception as e:
    print(f"Error: {e}")

# Test trades API for tick-level data (for pocket pivot logic)
print("\n=== MARKET EQUITY TRADES (VCI) ===")
try:
    eq = Market().equity(symbol="VCI")
    df = eq.trades(source="kbs", count=20)
    if isinstance(df, pd.DataFrame):
        print(f"Shape: {df.shape}, Columns: {list(df.columns)}")
        print(df.head(3).to_string())
except Exception as e:
    print(f"Error: {e}")
