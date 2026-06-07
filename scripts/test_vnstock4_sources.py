#!/usr/bin/env python3
"""Test vnstock4 OHLCV with different data sources."""
import warnings
warnings.filterwarnings('ignore')

from vnstock import Market

# Test all available sources for VCI daily data
print("=== DAILY OHLCV - Testing Sources ===")
sources_to_try = ['kbs', 'vnai', 'fpt', 'tcbs', 'ssi']
eq = Market().equity(symbol="VCI")

for source in sources_to_try:
    try:
        df = eq.ohlcv(start="2026-05-01", end="2026-05-31", resolution="1D", count=5, source=source)
        if hasattr(df, 'shape'):
            print(f"  {source:10s}: shape={df.shape} - OK")
            print(f"               cols={list(df.columns)}")
        else:
            print(f"  {source:10s}: non-DataFrame result ({type(df).__name__}): {str(df)[:80]}")
    except Exception as e:
        err_msg = str(e)
        if 'Dữ liệu' in err_msg:
            print(f"  {source:10s}: Empty data (quota or source unavailable)")
        else:
            print(f"  {source:10s}: Error - {err_msg[:80]}")

# Test intraday with all sources
print("\n=== INTRADAY OHLCV - Testing Sources ===")
intraday_intervals = ['1M', '5M', '15M', '30M']
for interval in intraday_intervals:
    for source in sources_to_try[:2]:  # Just test first 2 sources
        try:
            df = eq.ohlcv(start="2026-05-30", end="2026-05-31", resolution=interval, count=20, source=source)
            if hasattr(df, 'shape'):
                print(f"  {interval:4s}/{source:10s}: shape={df.shape} - OK")
            else:
                print(f"  {interval:4s}/{source:10s}: non-DataFrame")
        except Exception as e:
            err = str(e)
            if 'Dữ liệu' in err or 'trống' in err:
                print(f"  {interval:4s}/{source:10s}: Empty data")
print("\nDone testing sources and intervals.")
