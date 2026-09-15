#!/usr/bin/env python3
"""Fix tier_llm_analyst.py by rewriting the _clean_reasoning_preamble function."""

path = "/Users/nghialam/jarvis-hub/core/tier_llm_analyst.py"

with open(path) as f:
    lines = f.readlines()

# Find boundaries
start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if "def _clean_reasoning_preamble" in line:
        start_idx = i
    elif start_idx is not None and "def call_ollama" in line:
        end_idx = i - 1
        break

if start_idx is None or end_idx is None:
    print("Could not find function boundaries")
    exit(1)

print(f"Replacing lines {start_idx+1} to {end_idx+1}")

new_func = [
    "def _clean_reasoning_preamble(text):\n",
    '    """Remove Qwen3.6 reasoning preamble from streaming output."""\n',
    "    import re\n",
    "    lines = text.split('\\n')\n",
    "    skip_patterns = [\n",
    "        \"here's a thinking process\",\n",
    '        "let me think about this",\n',
    '        "i need to analyze",\n',
    "        \"as an ai, i don't have\",\n",
    "    ]\n",
    "    start_idx = 0\n",
    "    for line in lines:\n",
    "        lower = line.lower().strip()\n",
    "        if any(p in lower for p in skip_patterns):\n",
    "            start_idx += 1\n",
    "        else:\n",
    "            break\n",
    "    result = '\\n'.join(lines[start_idx:])\n",
    "    return result.strip() if result.strip() else text\n",
    "\n",
    "\n",
]

new_lines = lines[:start_idx] + new_func + lines[end_idx+1:]
new_content = "".join(new_lines)

# Write back
with open(path, 'w') as f:
    f.write(new_content)

# Validate syntax
import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("✓ SYNTAX VALID")
except py_compile.PyCompileError as e:
    msg = str(e)
    print(f"✗ BROKEN at line {e.lineno}: {msg}")
    # Show context lines
    error_line = e.lineno - 1
    for i in range(max(0, error_line-3), min(len(new_lines), error_line+4)):
        marker = " >>>" if i == error_line else "      "
        print(f"{marker} {i+1}: {new_lines[i]}")
