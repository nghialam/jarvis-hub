#!/usr/bin/env python3
"""Simple surgical fix for market_data.py function."""

PATH = "/Users/nghialam/jarvis-hub/scripts/trading_bot/market_data.py"

with open(PATH, "r") as f:
    lines = f.readlines()

# Find the target function and next def
start = None
end = None

for i, line in enumerate(lines):
    if "_load_watchlist_symbols" in line and "def " in line and start is None:
        start = i
    elif start is not None and end is None:
        s = line.strip()
        if s.startswith("def ") or s.startswith("class "):
            # Count blank lines between old func and this def
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            end = j + 1  # last non-blank line before next def
            break

print(f"Replace lines {start+1}-{end} ({end-start+1} lines)")

# Build new function
NEW_LINES = [
    "def _load_watchlist_symbols():\n",
    '    """Load watchlist from unified DB.\n',
    "\n",
    "    Falls back to hardcoded list if DB query fails.\n",
    '    """\n',
    "    try:\n",
    "        import sys as _sys\n",
    "        _sys.path.insert(0, os.path.dirname(__file__))\n",
    "        from db_watchlist import get_symbols_for_asset_type\n",
    "\n",
    "        # Fetch all symbols regardless of asset type\n",
    "        all_symbols = []\n",
    '        for atype in ("VN_STOCK", "US_EQUITY", "CRYPTO", "ETF", "OTHER"):\n',
    "            all_symbols.extend(get_symbols_for_asset_type(atype))\n",
    "\n",
    "        if all_symbols:\n",
    "            return all_symbols\n",
    "    except Exception as e:\n",
    '        print(f"[WARN] _load_watchlist_symbols DB error, fallback: {e}", file=sys.stderr)\n',
    "\n",
    "    # Fallback default list\n",
    '    return ["VCI","VIC","VCB","DGW","FTS","TCB","HCM","PDR","NLG","DXG",\n',
    '               "BMP","VGI","FRT","VIX","CTD","MBB","FPT","VHM","PVS","EVF","AAPL","MSFT","TSLA","BTC"]\n',
]

# Verify indentation
print("\nNew function indentation:")
for i, line in enumerate(NEW_LINES):
 stripped = line.lstrip()
 if any(kw in stripped[:30] for kw in ["def ", "try:", "except", "return [\"VCI"]):
     spaces = len(line) - len(stripped)
     print(f"  Line {i+1}: {spaces:2d} spaces | {stripped[:50]}")

# Replace
new_all = lines[:start] + NEW_LINES + ["\n"] + (["\n"] + lines[end:] if end else [])

with open(PATH, "w") as f:
    f.writelines(new_all)

print(f"\nDone. {len(new_all)} lines total.")

# Verify syntax
import ast
try:
    content = "".join(new_all)
    ast.parse(content)
    print("Syntax: OK!")
except SyntaxError as e:
    print(f"FAILED at L{e.lineno}: {e.msg}")
    ctx = max(0, e.lineno-3)
    for i in range(ctx, min(len(new_all), e.lineno+5)):
        m = ">>>" if (i+1)==e.lineno else "   "
        print(f"{m} L{i+1}: {new_all[i][:70]}")
