#!/usr/bin/env python3
"""Test vnstock4 intraday — try different approaches for 5-min candles."""
import warnings
warnings.filterwarnings('ignore')

from vnstock import Market
import pandas as pd

eq = Market().equity(symbol="VCI")

# Test 1: Try with vnai source + different interval notations  
print("=== Testing intervals with kbs source ===")
intervals = ['1D', '1d', '5M', '5m', '1M', '1m']
for interval in intervals:
    try:
        df = eq.ohlcv(start="2026-05-30", end="2026-05-31", resolution=interval, count=5)
        if isinstance(df, pd.DataFrame) and len(df) > 0:
            print(f"  {interval:4s}: shape={df.shape} ✓")
            print(f"           Time range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")
        else:
            print(f"  {interval:4s}: Empty DataFrame")
    except Exception as e:
        err = str(e)
        if 'Dữ liệu' in err or 'trống' in err:
            print(f"  {interval:4s}: No data available for this interval ({err[:60]})")

# Test 2: Check what vnai source provides (maybe it has real-time)
print("\n=== VNAI source quote test ===")
try:
    q = Market().quote(symbol="VCI", exchange="HOSE", source="vnai")
    if isinstance(q, pd.DataFrame):
        print(f"Quote shape: {q.shape}")
        print(f"Quote cols: {list(q.columns)}")
        print(q.to_string())
    else:
        print(f"Quote type: {type(q)} - {str(q)[:300]}")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Try kbs with much smaller range (single day)
print("\n=== Single day, multiple intervals ===")
for interval in ['1D', '5M', '1H']:
    try:  
        df = eq.ohlcv(start="2026-05-29", end="2026-05-29", resolution=interval, count=50)
        if isinstance(df, pd.DataFrame):
            print(f"  {interval}: {len(df)} rows")
            print(f"           {df.head(3).to_string()}")
    except Exception as e:
        err = str(e)
        if 'Dữ liệu' in err or 'trống' in err:
            print(f"  {interval}: No intraday data from kbs provider")
