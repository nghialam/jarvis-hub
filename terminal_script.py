#!/usr/bin/env python3
"""Remove 24 duplicate /api/v1/* routes from app.py"""

import re

app_path = '/Users/nghialam/jarvis-hub/app.py'
bak_path = app_path + '.bak.20260916'

# Back up first
with open(app_path, 'rb') as f:
    import shutil
    shutil.copy2(app_path, bak_path)
print(f"✅ Backed up to {bak_path}")

with open(app_path, 'r') as f:
    lines = f.readlines()

# Ranges to remove (end_line is exclusive):
ranges = [
    (1875, 1957),   # news/score (remove last to first to avoid line shift)
    (1859, 1873),   # market/auto-refresh/trigger
    (1799, 1857),   # market/heatmap
    (1718, 1759),   # portfolio/pnl-summary
    (1708, 1716),   # portfolio/delete-txn
    (1686, 1706),   # portfolio/add-txn
    (1671, 1684),   # portfolio/transactions
    (1650, 1669),   # portfolio/holdings
    (1635, 1648),   # watchlist/portfolio/remove
    (1618, 1633),   # watchlist/portfolio/add
    (1605, 1616),   # watchlist/portfolio
    (1592, 1603),   # research/crawl
    (1579, 1590),   # research/stats
    (1562, 1577),   # research
    (1539, 1560),   # companies/<symbol>/news
    (1518, 1537),   # companies
    (1504, 1516),   # news/trending
    (1478, 1502),   # news
    (1462, 1476),   # overview/chart
    (1443, 1460),   # overview/motions
    (1432, 1441),   # overview/gold
    (1417, 1430),   # overview/crypto
    (1398, 1415),   # overview/indices
    (1382, 1396),   # overview
]

# Sort ranges in reverse order (bottom of file first)
ranges.sort(key=lambda r: r[0], reverse=True)

# Remove ranges (1-indexed to 0-indexed, end exclusive)
removed = 0
for start, end in ranges:
    start_0 = start - 1  # 0-indexed
    # Include trailing blank lines
    end_0 = end  # already exclusive
    
    # Check if there's a trailing blank line after the function
    while end_0 < len(lines) and lines[end_0].strip() == '':
        end_0 += 1
    
    count = end_0 - start_0
    removed += count
    route = lines[start_0].strip()
    print(f"  Removed line {start}-{end-1}: {route}")
    del lines[start_0:end_0]

print(f"\n✅ Removed {removed} lines total")
print(f"   Before: {len(lines) + removed} lines → After: {len(lines)} lines")

# Write back
with open(app_path, 'w') as f:
    f.writelines(lines)

# Verify syntax
import py_compile
try:
    py_compile.compile(app_path, doraise=True)
    print("✅ Syntax check passed")
except py_compile.PyCompileError as e:
    print(f"❌ Syntax error: {e}")
    print(f"   Restored from backup")
    import shutil
    shutil.copy2(bak_path, app_path)
