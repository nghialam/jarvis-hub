#!/usr/bin/env python3
"""Fix market_data.py with raw bytes for EXACT indentation control."""

PATH = "/Users/nghialam/jarvis-hub/scripts/trading_bot/market_data.py"

def build_function():
    """Build the function using explicit space counting to avoid all string issues."""
    lines = [
        "def _load_watchlist_symbols():",
        "     \"\"\"Load watchlist from unified DB.",
        "",
        "    Falls back to hardcoded list if DB query fails.",
        "     \"\"\"",
        "    try:",
        "        import sys as _sys",
        "        _sys.path.insert(0, os.path.dirname(__file__))",
        "        from db_watchlist import get_symbols_for_asset_type",
        "",
        "        # Fetch all symbols regardless of asset type",
        "        all_symbols = []",
        '        for atype in ("VN_STOCK", "US_EQUITY", "CRYPTO", "ETF", "OTHER"):',
        "            all_symbols.extend(get_symbols_for_asset_type(atype))",
        "",
        "        if all_symbols:",
        "            return all_symbols",
        "    except Exception as e:",
        '        print(f"[WARN] _load_watchlist_symbols DB error, fallback: {e}", file=sys.stderr)',
        "",
        "     # Fallback default list", 
        '"return ["VCI","VIC","VCB","DGW","FTS","TCB","HCM","PDR","NLG","DXG",',
        '         "BMP","VGI","FRT","VIX","CTD","MBB","FPT","VHM","PVS","EVF","AAPL","MSFT","TSLA","BTC"]'
    ]
    
    # Verify each line's leading spaces
    print("Function bytes (spaces before first non-space char):")
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        sp = len(line) - len(stripped) if stripped else 0
        if any(kw in stripped[:50] for kw in ["def _load", "try:", "except", "return [\"VCI"]):
            print(f"  L{i+1:2d}: {sp:>2} spaces | {stripped[:60]}")
    
    return "\n".join(lines)

func = build_function()

# Read current file
with open(PATH, "r") as f:
    lines = f.readlines()

print(f"\nFile has {len(lines)} lines before replacement")

# Find function boundaries  
def_start = None
def_end = None

for i in range(len(lines)):
    if b"def _load_watchlist_symbols" in lines[i] if hasattr(lines[i], 'find') else lines[i].find("def _load_watchlist_symbols") != -1:
        def_start = i
    elif def_start is not None and def_end is None:
        stripped = lines[i].strip()
        if (stripped.startswith("def ") or stripped.startswith("class ")) and len(stripped) > 0:
            # Find last blank line before next def
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            def_end = j + 1
            break

if def_start is None:
    print("ERROR: function not found")
    exit(1)

print(f"Replacing lines {def_start+1} to {'EOF' if def_end is None else str(def_end+1)}")

# Build new file content  
before = "".join(lines[:def_start])
body = func + "\n\n\n"
after = "" if def_end is None else "".join(lines[def_end:])

new_content = before + body + after

with open(PATH, "w") as f:
    f.write(new_content)

print(f"Wrote {len(new_content.split(chr(10)))} lines total")

# Verify syntax  
import ast
try:
    ast.parse(new_content)
    print("Syntax check: PASSED OK!")
except SyntaxError as e:
    print(f"FAILED at L{e.lineno}: {e.msg}")
