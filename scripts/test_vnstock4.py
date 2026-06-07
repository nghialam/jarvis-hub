#!/usr/bin/env python3
"""Test vnstock4 APIs for jarvis-hub migration."""
import warnings
warnings.filterwarnings('ignore')

from vnstock import Market, Listing
import pandas as pd

# Test 1: Market.quote for real-time data
print("=== MARKET QUOTE (VCI) ===")
try:
    q = Market().quote(symbol="VCI", exchange="HOSE")
    print(f"Type: {type(q)}")
    if isinstance(q, pd.DataFrame):
        print(q.head(3).to_string())
        print(f"Cols: {list(q.columns)}")
    elif hasattr(q, 'get'):
        print(f"Keys: {list(q.keys())}")
        print(f"Sample: {str(q)[:500]}")
    else:
        print(str(q)[:500])
except Exception as e:
    print(f"Error: {e}")

# Test 2: Market.equity for historical/candle data  
print("\n=== MARKET EQUITY (VCI) ===")
try:
    equity = Market().equity(symbol="VCI")
    print(f"Type: {type(equity)}")
    if hasattr(equity, 'history'):
        h = equity.history(date_from="2025-05-01", date_to="2026-05-31")
        print(f"\nHistory type: {type(h)}")
        if isinstance(h, pd.DataFrame):
            print(h.tail(3).to_string())
            print(f"Cols: {list(h.columns)}")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Search for symbols  
print("\n=== LISTING / SEARCH ===")
try:
    l = Listing()
    result = l.search_symbol("VCI")
    print(f"Search type: {type(result)}")
    print(str(result)[:500])
except Exception as e:
    print(f"Error: {e}")
