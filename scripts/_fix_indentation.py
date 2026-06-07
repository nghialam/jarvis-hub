#!/usr/bin/env python3
"""Properly fix app.py by auto-detecting and fixing indentation for every line."""
import shutil
import py_compile

PATH = "/Users/nghialam/jarvis-hub/app.py"

# Read corrupted file  
with open(PATH, "r") as f:
    raw_lines = f.readlines()

print("Read %d lines" % len(raw_lines))

# Strategy:
# 1. Remove excessive blank lines (keep max 2 consecutive)  
# 2. Fix docstring indentation to match project style (3-4 spaces)
# 3. Keep regular code as-is since backup has correct structure except docstrings

cleaned = []
blank_count = 0

for line in raw_lines:
    stripped = line.rstrip("\n\r")
    
    # 1. Handle blank lines
    if not stripped.strip():
        blank_count += 1
        if blank_count <= 2:
            cleaned.append("")
        continue
    blank_count = 0
    
    # Get actual indentation and content
    leading_ws = len(stripped) - len(stripped.lstrip())
    code = stripped.lstrip()
    
    # 2. Fix docstrings (should be 3-4 spaces not 5+)
    if code.startswith('"""'):
        if leading_ws >= 6:
            code = '    ' + code[3:]
        elif leading_ws == 5:
            code = '    ' + code[3:]  
        cleaned.append(code)
        continue
    
    # 3. Keep regular code lines as-is
    cleaned.append(code)

content = "\n".join(cleaned)

fix_count = sum(1 for l in cleaned if l.strip().startswith('"""'))

print("Fixed %d docstring indentations" % fix_count)

# Backup (Golden Rule!)
shutil.copy2(PATH, PATH + ".bak.pre_final_fix")

with open(PATH, "w") as f:
    f.write(content)
    
print("Wrote %d lines total to path" % len(cleaned))

# Test syntax - show FIRST error only  
try:
    py_compile.compile(PATH, doraise=True)
    print("\nOK! Syntax check PASSED!")
except SyntaxError as e:
    lines = content.split("\n")
    print("\nFIRST SYNTAX ERROR at line %d: %s" % (e.lineno, e.msg))
    start = max(0, e.lineno - 5)
    for i in range(start, min(len(lines), e.lineno + 6)):
        marker = ">>> " if i+1 == e.lineno else "     "
        indent = len(lines[i]) - len(lines[i].lstrip()) if lines[i].strip() else '---'
        print("%s L%d (%4s): %s" % (marker, i+1, indent, lines[i][:100]))
