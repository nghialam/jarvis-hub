#!/usr/bin/env python3
"""Test cleaning logic on actual output and improve it."""

# Simulate the Qwen3.6 reasoning output we've been getting
example_output = """1.    **Analyze User Input:**
    - **Data Provided:**
        - VN Stocks (prices in VND): ACB (1087.7), FPT (315.2)...
        - Market Indices: DJIA (51920.62), S&P500 (7354.02

2.    **VN Stock Performance:**
    - Overall trend: Downward
    High-priced stocks like ACB ...

3.    **Sector Analysis:**
    - Banking sector showing weak momentum...

## Actual analysis content starts here
This is proper market analysis"""

import re

def _clean_reasoning_preamble(text):
      """Remove Qwen3.6 reasoning preamble from streaming output."""
    lines = text.split("\n")
    skip_patterns = [
        "here's a thinking process",
        "let me think about this",
            "i need to analyze",
            "as an ai, i don't have",
            "**Analyze User Input**:",
            "**Role:** Financial",
            "**Data Provided:**",
    ]
    skip_count = 0
    for line in lines:
        lower_line = line.lower().strip()
            # Skip numbered reasoning steps like "1. **Text**"
        if re.match(r'^\s*\d+\.\s+\*\*', line):
            skip_count += 1
        elif any(p in lower_line for p in skip_patterns):
            skip_count += 1
        else:
            break
    result = "\n".join(lines[skip_count:])
    return result.strip() if result.strip() else text

result = _clean_reasoning_preamble(example_output)
print("=== After cleaning ===")
print(result[:400])
print("...")

# The issue: reasoning steps are numbered 1, 2, 3 which ARE actual analysis structure
# Numbered lists in the analysis (VN stocks, sector, etc.) will also be matched.
# 
# Better approach: skip ONLY the opening reasoning preamble then take the rest.
# The preamble is usually 2-8 lines of model's internal chain-of-thought.
# After that is the actual response.

print("\n=== Attempting better detection ===")

def _clean_reasoning_preamble_v2(text):
        # Qwen3.6 reasoning models output thinking content before final response
    # Common patterns: "Here's a thinking process:", numbered lists of steps, role/data analysis
    # The actual useful content starts after the model stops analyzing its own input
    
    lines = text.split("\n")
    
    # Strategy 1: Skip numbered reasoning blocks at start followed by another pattern
    skip_to = 0
    for i in range(min(len(lines), 20)):  # Only check first 20 lines for preamble
        if re.match(r'^\s*\d+\.\s+\*\*', lines[i]) or \
            any(p in lines[i].lower() for p in [
                "here's a thinking process",
                "**analyze user input**",
                "**role:** financial",
                "**data provided**",
            ]):
            skip_to = i + 1
        elif re.match(r'^\s*\d+\.\s+', lines[i]) and skip_to > 0:
            # Numbered list continuing preamble
            skip_to = i + 1
    
    if skip_to > 0:
        return "\n".join(lines[skip_to:]).strip()
    return text.strip()

result2 = _clean_reasoning_preamble_v2(example_output)
print("\n=== After cleaning (v2) ===")
print(result2[:400])

