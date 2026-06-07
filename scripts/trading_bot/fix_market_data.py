#!/usr/bin/env python3
"""Fix market_data.py by writing the EXACT bytes for _load_watchlist_symbols."""

PATH = "/Users/nghialam/jarvis-hub/scripts/trading_bot/market_data.py"

# Build the function with EXACT bytes - no string ambiguity
B4   = b'     '       # 4 spaces
B8   = B4 + B4        # 8 spaces total  
B12  = B8 + B4        # 12 spaces total
NEWLINE = b'\n'

func_bytes = b''
func_bytes += b'def _load_watchlist_symbols():\n'
# Docstring: indented 4 spaces
func_bytes += B4 + b'"""Load watchlist from unified DB.\n'
func_bytes += NEWLINE
func_bytes += B4 + b'    Falls back to hardcoded list if DB query fails.\n'
func_bytes += B4 + b'"""\n'
# try: block - indented 4 spaces
func_bytes += B4 + b'try:\n'
# Inside try - indented 8 spaces
func_bytes += B8 + b'import sys as _sys\n'
func_bytes += B8 + b'_sys.path.insert(0, os.path.dirname(__file__))\n'
func_bytes += B8 + b'from db_watchlist import get_symbols_for_asset_type\n'
func_bytes += NEWLINE
# Comment inside try - 8 spaces (same level as imports)  
func_bytes += B8 + b'# Fetch all symbols regardless of asset type\n'
func_bytes += B8 + b'all_symbols = []\n'
func_bytes += B8 + b'for atype in ("VN_STOCK", "US_EQUITY", "CRYPTO", "ETF", "OTHER"):\n'
func_bytes += B12 + b'all_symbols.extend(get_symbols_for_asset_type(atype))\n'
func_bytes += NEWLINE
func_bytes += B8 + b'if all_symbols:\n'
func_bytes += B12 + b'return all_symbols\n'
# except block - 4 spaces (same level as try)
func_bytes += B4 + b'except Exception as e:\n'
func_bytes += B8 + b'print(f"[WARN] _load_watchlist_symbols DB error, fallback: {e}", file=sys.stderr)\n'
func_bytes += NEWLINE
# Final return - 4 spaces (same level as try)
func_bytes += B4 + b'# Fallback default list\n'
func_bytes += B4 + b'return ["VCI","VIC","VCB","DGW","FTS","TCB","HCM","PDR","NLG","DXG",\n'
func_bytes += B12 + b'"BMP","VGI","FRT","VIX","CTD","MBB","FPT","VHM","PVS","EVF","AAPL","MSFT","TSLA","BTC"]\n'

# Read the current file
with open(PATH, 'rb') as f:
    original = f.read()

lines = original.split(b'\n')

# Find function boundaries (0-indexed byte positions)
def_start = None
def_end = None

for i in range(len(lines)):
    if b'def _load_watchlist_symbols' in lines[i] and def_start is None:
        def_start = i
    elif def_start is not None and def_end is None:
        stripped = lines[i].strip()
        if (stripped.startswith(b'def ') or stripped.startswith(b'class ')) and len(stripped) > 0:
            # Include blank lines before next def, exclude the def line itself
            def_end = i - 1
            break

if def_start is None:
    print("ERROR: function not found")
    exit(1)

print(f"Replacing lines {def_start+1} to {def_end if def_end else 'EOF'}")

# Build new content: everything before def + new func + blank lines + everything after
before = b'\n'.join(lines[:def_start]) 
after_lines = ([''] * 3) if def_end is not None and def_end < len(lines) else []
# Skip the blank line(s) between old function and next def to avoid double blank
if after_lines:
     while def_end >= 0 and not lines[def_end].strip():
         def_end -= 1
    after = b'\n'.join(lines[def_end+1:])
else:
    after = b''

new_content = before + func_bytes + after

with open(PATH, 'wb') as f:
    f.write(new_content)

# Verify syntax
import ast
new_text = new_content.decode('utf-8')
try:
    ast.parse(new_text)
    print("✓ Syntax check PASSED")
except SyntaxError as e:
    print(f"✗ Syntax error at L{e.lineno}: {e.msg}")
    # Show context
    nl = new_text.split('\n')
    start = max(0, e.lineno - 5)
    end = min(len(nl), e.lineno + 5)
    for i in range(start, end):
        marker = " >>>" if i+1 == e.lineno else "     "
        print(f"{marker} L{i+1}: {nl[i][:80]}")
