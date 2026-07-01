#!/usr/bin/env python3
"""Patch llm_evaluation.py streaming handler - version 2."""

FILEPATH = '/Users/nghialam/jarvis-hub/core/llm_evaluation.py'

with open(FILEPATH, 'r') as f:
    lines = f.readlines()

changed = []

# 1. Add import json if missing before def load_db_data
found_json = any('import json' in l.strip() for l in lines[:200])
if not found_json:
    for i, line in enumerate(lines):
        if 'import os' in line and 'path' in line:
            lines.insert(i + 1, 'import json\n')
            changed.append(f"Added import json at line {i+2}")
            break

# 2. Fix stream: False to True
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('"stream":'):
        # Get indent from original line
        indent = len(line) - len(line.lstrip())
        lines[i] = ' ' * indent + '"stream": True,\n'
        changed.append(f"Set stream=True at line {i+1}")

# 3. Replace response parsing block
for i, line in enumerate(lines):
    if 'if r.status_code == 200:' in line:
        # Get base indent of the if block
        base_indent = len(line) - len(line.lstrip())
        
        # Find end of this block (next def or non-indented at same level)
        j = i + 1
        while j < len(lines):
            stripped_j = lines[j].strip()
            if not stripped_j:
                j += 1
                continue
            cur_indent = len(lines[j]) - len(lines[j].lstrip())            # Block ends when we hit same/lesser indent (but skip blank lines above)            if cur_indent <= base_indent and (cur_indent == base_indent or not stripped_j.startswith('if')):
                break            j += 1
        
        block_end = j
        print(f"Replacing response parsing at lines {i+1}-{block_end}")
        
        # Build replacement - use list of lines directly
        new_block = [
            f'{" " * base_indent}full_text = []\n',
            f'{" " * base_indent}for chunk_line in r.iter_lines():\n',
            f'{" " * (base_indent + 4)}if not chunk_line.strip():\n',
            f'{" " * (base_indent + 8)}continue\n',
            f'{" " * (base_indent + 4)}try:\n',
            f'{" " * (base_indent + 8)}chunk = json.loads(chunk_line)\n',
            f'{" " * (base_indent + 8)}delta = chunk.get("message", {{}}).get("content", "")\n',
            f'{" " * (base_indent + 8)}if delta:\n',
            f'{" " * (base_indent + 12)}full_text.append(delta)\n',
            f'{" " * (base_indent + 4)}except (json.JSONDecodeError, KeyError):\n',
            f'{" " * (base_indent + 8)}pass\n',
            f'\n',
            f'{" " * base_indent}return "".join(full_text).strip()\n',
        ]
        
        # Replace the block        rest = lines[block_end:]
        lines = lines[:i] + new_block + rest
        
        changed.append(f"Applied streaming parser at line {i+1}")
        break

# Write back
with open(FILEPATH, 'w') as f:
    f.writelines(lines)

print("\nChanges made:")
for c in changed:
    print(f"  ✓ {c}")

# Validate syntax
import ast
try:
    content = ''.join(lines)
    ast.parse(content)
    print("\n✅ Syntax OK")
except SyntaxError as e:
    print(f"\n❌ Syntax Error at line {e.lineno}: {e.msg}")
    lines_new = content.split('\n')
    for ln in range(max(0, e.lineno - 3), min(len(lines_new), e.lineno + 2)):
        marker = ">>>" if ln == e.lineno - 1 else "    "
        print(f"{marker} {ln+1:4d}: {lines_new[ln][:80]}")
