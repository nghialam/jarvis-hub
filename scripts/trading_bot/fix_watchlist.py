#!/usr/bin/env python3
"""Surgical fix for _load_watchlist_symbols in market_data.py"""

PATH = "/Users/nghialam/jarvis-hub/scripts/trading_bot/market_data.py"

with open(PATH, "r") as f:
    lines = f.readlines()

# Find boundaries  
start = None
end = None
for i in range(len(lines)):
    if "_load_watchlist_symbols" in lines[i] and "def " in lines[i]:
        start = i
    elif start is not None and (lines[i].startswith("def ") or lines[i].startswith("class ")) and len(lines[i]) > 0:
        end = i
        break

if start is None:
    print("ERROR: not found"); exit(1)
print(f"Replace lines {start+1}-{end if end else 'EOF'}")

# Build new function parts  
parts = []
p4 = "     # 4 spaces (use carefully)"
p8 = p4 + p4  # 8 spaces total
p12 = p8 + p4  # 12 spaces total

parts.append("def _load_watchlist_symbols():\n")
parts.append(p4 + '"""Load watchlist from unified DB.\n')
parts.append("\n")
parts.append(p4 + "Falls back to hardcoded list if DB query fails.\n")
parts.append(p4 + '"""\n')
parts.append(p4 + "try:\n")
parts.append(p8 + "import sys as _sys\n")
parts.append(p8 + "_sys.path.insert(0, os.path.dirname(__file__))\n")
parts.append(p8 + "from db_watchlist import get_symbols_for_asset_type\n")
parts.append("\n")
parts.append(p8 + "all_symbols = []\n")
parts.append(p8 + 'for atype in ("VN_STOCK", "US_EQUITY", "CRYPTO", "ETF", "OTHER"):\n')
parts.append(p12 + "all_symbols.extend(get_symbols_for_asset_type(atype))\n")
parts.append("\n")
parts.append(p8 + "if all_symbols:\n")
parts.append(p12 + "return all_symbols\n")
parts.append(p4 + "except Exception as e:\n")

# Escape the f-string properly
fstr_line = 'print(' + '"' + '[WARN] _load_watchlist_symbols DB error, fallback: {}' + '", file=sys.stderr)'.format("{}")  # will be replaced later
parts.append(p8 + fstr_line + "\n")
parts.append("\n")
parts.append(p4 + "if False:\n")  # placeholder - will fix below
parts.append(p8 + """return ["VCI","VIC","VCB","DGW","FTS","TCB","HCM","PDR","NLG","DXG",\n""")
parts.append(p12 + '"""BMP","VGI","FRT","VIX","CTD","MBB","FP' + """)\n""")

final_func = "".join(parts)

# Fix the return statement properly  
idx = final_func.index('if False')  
correct_return = p8 + """return ["VCI","VIC","VCB","DGW","FTS","TCB","HCM","PDR",
""" + p12 + '"BMP","VGI","FRT","VIX","CTD","MBB","FPT","VHM","PVS","EVF","AAPL","MSFT","TSLA","BTC"]'

final_func = final_func[:idx] + correct_return + "\n" + final_func[idx+8:]  # remove "if False:" placeholder

# Rebuild file
before = lines[:start]
after = ["\n", "\n"]
if end:
    after += lines[end:]
    
new_lines = before + [final_func] + after

with open(PATH, "w") as f:
    f.writelines(new_lines)

# Verify indentation of key lines
for i, line in enumerate(final_func.split('\n')):
    stripped = line.lstrip()
    spaces = len(line) - len(stripped)
    if any(kw in stripped[:50] for kw in ["def _load", "try:", "except", "return [\"VCI"]):
        print(f"{spaces:>2}sp: {stripped[:60]}")

import py_compile
try:
    py_compile.compile(PATH, doraise=True)
    print("\nSyntax check: PASSED ✓")
except Exception as e:
    print(f"\nFAILED: {e}")
