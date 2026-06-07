#!/usr/bin/env python3
"""Fix indentation in Jarvis signals API endpoints."""

import re

PATH = "/Users/nghialam/jarvis-hub/app.py"

with open(PATH, "r") as f:
    lines = f.readlines()

# Find the start of signals section
signals_start = None
for i, line in enumerate(lines):
    if "# Unified Signals Feed" in line:
        signals_start = i
        print(f"Found signals section at line {i+1}")
        break

if signals_start is None:
    print("ERROR: Could not find signals section")
    exit(1)

# The old alerts section start (where signals section ends)
alerts_start = None
for i in range(signals_start + 5, len(lines)):
    if "# Trading Alert Feed - NEW FEATURE" in lines[i]:
        alerts_start = i - 2  # Include the blank lines before
        print(f"Old alert section starts at line {i+1}")
        break

if alerts_start is None:
    alerts_start = len(lines)

# Process each line in signals section
fixed = []
for i in range(signals_start, alerts_start):
    line = lines[i]
    
    # Skip comment lines as-is
    if line.strip().startswith("#"):
        fixed.append(line)
        continue
    
    # Find actual indentation (count leading spaces)
    stripped = line.lstrip()
    indent = len(line) - len(stripped)
    
    # Fix docstrings: remove extra 2 spaces before """
    if stripped.startswith('"""') and indent >= 6:
        # This is a docstring, reduce to 4 spaces
        fixed.append(" " * 4 + stripped)
        continue
    
    # Fix body inside functions: ensure proper 8-space indentation for body lines
    if indent == 6 and stripped and not stripped.startswith("#"):
        # Lines with exactly 6 spaces that are actually function body go to 8
        fixed.append(" " * 8 + stripped)
    elif indent == 8 and stripped and not stripped.lstrip().startswith("#") and "def " not in line:
        # Keep 8-space as-is (correct for function body)
        fixed.append(line)
    else:
        # Most other lines as-is
        fixed.append(line)

print(f"Fixed {len(fixed)} lines")

# Write back with proper structure
before = lines[:signals_start]
after = [lines[alerts_start]] if alerts_start < len(lines) else []

new_content = "".join(before) + "\n".join(fixed) + "\n\n" + "".join(after)

with open(PATH, "w") as f:
    f.write(new_content)

print("Written back to app.py")

# Verify syntax
try:
    import py_compile
    py_compile.compile(PATH, doraise=True)
    print("\n✅ Syntax validation: PASSED!")
except SyntaxError as e:
    print(f"\n❌ SYNTAX ERROR at line {e.lineno}: {e.msg}")
    ctx = new_content.split('\n')
    start = max(0, e.lineno - 5)
    for i in range(start, min(len(ctx), e.lineno + 5)):
        marker = " >>>" if i+1 == e.lineno else "      "
        print(f"{marker} L{i+1}: {ctx[i][:90]}")
