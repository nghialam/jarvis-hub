#!/usr/bin/env python3
"""Fix ONLY the /api/indices endpoint in app.py."""
filepath = '/Users/nghialam/jarvis-hub/app.py'

with open(filepath, 'r') as f:
    lines = f.readlines()

start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if '@app.route("/api/indices"' in line:
        start_idx = i
    elif start_idx is not None and i > start_idx + 2:
        stripped = line.strip()
        if stripped.startswith('@app.route') or (stripped and not line[0].isspace()):
            end_idx = i
            break

if start_idx is None or end_idx is None:
    print("Could not find /api/indices endpoint boundaries")
    exit(1)

print(f"Replacing lines {start_idx+1} to {end_idx}")

new_code = '''@app.route("/api/indices", methods=["GET"])
def api_indices():
     """Fetch + return VN-Index + global market indices from DB."""
    try:
        if not db or not hasattr(db, "get_latest_overview"):
            return jsonify({
                 "vn_indices": {},
                 "global_indices": {},
                 "note": "DB not initialized — run Tier 1 data collection first"
             })
        overview = db.get_latest_overview() or {}
        vn_idx = overview.get("vn_indices", {}) or overview.get("VN-Index", {}) or {}
        glb = overview.get("global_indices", {}) or overview.get("Global", {}) or {}
         # Also try fallback from market_overview table
        if not vn_idx:
            for row in db._c().execute(
                 "SELECT symbol, price, change_pct FROM market_overview WHERE asset_type='index'").fetchall():
                vn_idx[row[0]] = {"price": row[1], "change_pct": row[2]}
        if not glb:
            for row in db._c().execute(
                 "SELECT symbol, price, change_pct FROM market_overview WHERE asset_type IN ('global','fx')").fetchall():
                glb[row[0]] = {"price": row[1], "change_pct": row[2]}
        return jsonify({
             "vn_indices": vn_idx,
             "global_indices": glb,
             "source": "DB",
             "updated_at": overview.get("updated_at", ""),
         })
    except Exception as e:
        print("[INDICES] DB fetch error: %s" % e)
        return jsonify({"vn_indices": {}, "global_indices": {}, "error": str(e)}), 502


'''

result = lines[:start_idx] + [new_code + "\n"] + lines[end_idx:]

with open(filepath, 'w') as f:
    f.writelines(result)

# Fix any mixed indentation in the new code block (normalize to multiples of 4)
content = ''.join(result)
fixed_lines = content.split('\n')
for i, line in enumerate(fixed_lines):
    if line.strip():  # not blank
        raw_indent = len(line) - len(line.lstrip(' '))
        expected = (raw_indent // 4) * 4
        if raw_indent != expected:
            fixed_lines[i] = ' ' * expected + line.lstrip(' ')

final = '\n'.join(fixed_lines)

# Write with guaranteed clean indentation
with open(filepath, 'w') as f:
    f.write(final)

# Validate syntax
import ast
try:
    ast.parse(final)
    print("✅ Syntax OK")
except SyntaxError as e:
    print(f"✗ Syntax Error at line {e.lineno}: {e.msg}")
