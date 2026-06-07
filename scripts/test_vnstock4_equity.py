#!/usr/bin/env python3
"""Test vnstock4 equity history OHLCV API."""
import warnings
warnings.filterwarnings('ignore')

from vnstock import Market, Listing
import pandas as pd

# Test equity.history for candle data
print("=== MARKET EQUITY HISTORY (VCI daily) ===")
try:
    equity = Market().equity(symbol="VCI")
    print(f"Equity object type: {type(equity)}")
    print(f"Equity dir: {[x for x in dir(equity) if not x.startswith('_')]}")
except Exception as e:
    print(f"Error getting equity: {e}")
    import traceback; traceback.print_exc()

print("\n=== TRYING HISTORY ===")
try:
    from vnstock.ui.domains.market.equity import EquityMarket
    # Look for history method
    eq = Market().equity(symbol="VCI")
    if hasattr(eq, 'history'):
        h = eq.history(date_from="2025-12-01", date_to="2026-05-31", interval="daily")
        print(f"\nHistory type: {type(h)}")
        if isinstance(h, pd.DataFrame):
            print(h.tail(5).to_string())
            print(f"Cols: {list(h.columns)}")
    else:
        # Try other method names
        methods = [m for m in dir(eq) if not m.startswith('_')]
        print(f"Available methods on eq: {methods}")
except Exception as e:
    print(f"Error: {e}")
    import traceback; traceback.print_exc()

# Also test the Listing provider directly 
print("\n=== LISTING SYMBOLS ===")
try:
    l = Listing()
    # Try symbols_by_exchange  
    hs = l.symbols_by_exchange("HOSE")
    print(f"HOSE symbols type: {type(hs)}")
    if hasattr(hs, 'head'):
        print(hs.head(3).to_string())
    else:
        print(str(hs)[:500])
except Exception as e:
    print(f"Error: {e}")
