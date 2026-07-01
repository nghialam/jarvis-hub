#!/usr/bin/env python3
"""Normalize all indents in a Python file to proper 4-space multiples."""
import sys
filepath = '/Users/nghialam/jarvis-hub/app.py'
with open(filepath, 'r') as f:
    content = f.read()
lines = content.split('\n')
for i in range(len(lines)):
    line = lines[i]
    if not line.strip():
        continue
    stripped = line.lstrip(' ')
    indent_spaces = len(line) - len(stripped)
    new_indent = (indent_spaces // 4) * 4
    if indent_spaces != new_indent:
        lines[i] = ' ' * new_indent + stripped
fixed_content = '\n'.join(lines)
with open(filepath, 'w') as f:
    f.write(fixed_content)
import ast
try:
    ast.parse(fixed_content)
    print("OK - app.py syntax validated")
except SyntaxError as e:
    print(f"ERROR line {e.lineno}: {e.msg}")
