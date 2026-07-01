#!/usr/bin/env python3
"""Normalize all indents in a Python file to proper 4-space multiples."""
import re
import sys

filepath = '/Users/nghialam/jarvis-hub/core/llm_evaluation.py'

with open(filepath, 'r') as f:
    content = f.read()

lines = content.split('\n')
for i in range(len(lines)):
    line = lines[i]
    if not line.strip():
        continue  # blank line, skip
    
     # Count leading spaces (only spaces, not tabs)
    stripped = line.lstrip(' ')
    indent_spaces = len(line) - len(stripped)
    
     # Normalize to multiple of 4
    new_indent = (indent_spaces // 4) * 4
    if indent_spaces != new_indent:
        lines[i] = ' ' * new_indent + stripped

fixed_content = '\n'.join(lines)

with open(filepath, 'w') as f:
    f.write(fixed_content)

# Validate syntax
import ast
try:
    ast.parse(fixed_content)
    print("OK - Syntax validated")
except SyntaxError as e:
    print(f"ERROR line {e.lineno}: {e.msg}")
    start = max(0, e.lineno - 3)
    end = min(len(lines), e.lineno + 2)
    for i in range(start, end):
        marker = ">>>" if i == e.lineno - 1 else "   "
        print(f"{marker} {i+1:4d}: {lines[i][:80]}")
