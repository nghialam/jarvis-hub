#!/usr/bin/env python3
"""Fix streaming parser indentation in llm_evaluation.py."""
filepath = '/Users/nghialam/jarvis-hub/core/llm_evaluation.py'
with open(filepath, 'r') as f:
    lines = f.readlines()

# Find the problematic streaming block start
for i in range(len(lines)):
    if '# Path 1: OpenAI-compatible SSE format' in lines[i]:
        print(f"Found streaming block at line {i+1}, fixing...")
        
         # Build correct replacement with consistent 4-space indent multiples
        new_block = [
            '                    deltas = chunk.get("choices", [{}])\n',
            '                    delta = deltas[0].get("delta", {}).get("content", "") if deltas else ""\n',
            '\n',
            '                    # Path 2: Ollama native SSE format (thinking mode)\n',
            '                    if not delta and "message" in chunk:\n',
            '                        msg = chunk["message"]\n',
            '                        delta = msg.get("content", "") or ""\n',
            '                        if not delta:\n',
            '                            delta = msg.get("thinking", "") or ""\n',
            '\n',
            '                    # Also extract thinking from top level\n',
            '                    if not delta and "thinking" in chunk:\n',
            '                        delta = chunk["thinking"] or ""\n',
            '\n',
            '                    if delta:\n',
            '                        full_text.append(delta)\n'
        ]
        
        # Keep the try: line and except block, replace everything in between
        rest = lines[i:]    # from "# Path 1..." to end of current block
        
        # Replace the old block with new one
        # Keep the "try:" line (it's before "# Path 1")
        fixed_lines = rest[:1] + new_block + rest[-2:]   # -2 keeps except block
        
        lines[i:i + len(rest)] = fixed_lines
        print(f"✅ Replaced {len(rest)} lines with {len(fixed_lines)} total")
        break

with open(filepath, 'w') as f:
    f.writelines(lines)

# Validate syntax
import ast
try:
    content = ''.join(lines)
    ast.parse(content)
    print("✅ Syntax OK - streaming parser fixed!")
except SyntaxError as e:
     print(f"❌ SYNTAX ERROR at line {e.lineno}: {e.msg}")
     all_lines = content.split('\n')
     for ln in range(max(0, e.lineno-3), min(len(all_lines), e.lineno+2)):
         marker = ">>>" if ln == e.lineno-1 else "     "
         print(f"{marker} {ln+1:4d}: {all_lines[ln][:80]}")
