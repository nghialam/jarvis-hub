#!/usr/bin/env python3
"""Clean up app.py indentation at the end."""
path = '/Users/nghialam/jarvis-hub/app.py'

with open(path, 'r') as f:
    lines = f.readlines()

# Find and fix the _init_server block (last ~15 lines)
new_lines = []
skip_until_main = False
for i, line in enumerate(lines):
    stripped = line.rstrip('\n').rstrip('\r')
    
    # Skip old broken block from _init_server onward
    if stripped.strip() == 'def _init_server():':
        skip_until_main = True
    
    if skip_until_main:
        # Find the if __name__ line
        if stripped.startswith('if __name__'):
            skip_until_main = False
            # Write clean block
            new_lines.append('\n')
            new_lines.append('\n')
            new_lines.append('def _init_server():\n')
            new_lines.append('    try:\n')
            new_lines.append('        _load_config()\n')
            new_lines.append('        _load_db()\n')
            new_lines.append('        _refresh_data()\n')
            new_lines.append('    except Exception as e:\n')
            new_lines.append('        print("[INIT] Error during init: %s" % e)\n')
            new_lines.append('\n')
            new_lines.append('\n')
            new_lines.append('# Run on import (for Flask app factory pattern)\n')
            new_lines.append('try:\n')
            new_lines.append('    _init_server()\n')
            new_lines.append('except Exception:\n')
            new_lines.append('    pass\n')
            new_lines.append('\n')
            new_lines.append('\n')
            new_lines.append('if __name__ == "__main__":\n')
            new_lines.append('    _init_server()\n')
            new_lines.append('    print("[APP] Starting Jarvis Hub Flask server on port 8100...")\n')
            new_lines.append('    app.run(host="0.0.0.0", port=8100, debug=False, use_reloader=False)\n')
        continue

    if not skip_until_main:
        new_lines.append(line)

with open(path, 'w') as f:
    f.writelines(new_lines)

print(f"Fixed app.py — {len(lines)} -> {len(new_lines)} lines")

# Verify
import py_compile
py_compile.compile(path, doraise=True)
print("Syntax check: OK ✅")
