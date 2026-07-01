#!/usr/bin/env python3
# Patch Prompt 1 in gotham_brief.py - AI & Tech Priority improvement
import re

src = '/Users/nghialam/jarvis-hub/scripts/gotham_brief.py'
with open(src, 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # Find the start of Prompt 1 system prompt
    if 'You are Jarvis, an intelligence analyst.' in line:
        new_lines.append('            f"""' + '\n')
        new_lines.append('You are Jarvis, a hedge-fund intelligence analyst. %DATE%\n')
        new_lines.append('\n')
        new_lines.append('PROVIDE EXACTLY these sections below:\n')
        new_lines.append('\n')
        new_lines.append('### NEWS SYNTHESIS\n')
        new_lines.append('\n')
        new_lines.append('Analyze ALL articles from the last 24 hours. For each significant AI/tech story discovered, provide:\n')
        new_lines.append('- [HEADLINE] <core insight in 1 line> | Revenue impact: $AMOUNT or N/A | Sectors affected: #AI #Semiconductors etc. | Confidence: HIGH / MED / LOW\n')
        new_lines.append('For non-AI/tech stories, group by sector theme and cross-reference with similar regional coverage.\n')
        new_lines.append('\n')
        new_lines.append('### TREND ANALYSIS\n')
        new_lines.append('\n')
        new_lines.append('Top 3 narrative themes from today: what triggered each? Which specific articles prove it?\n')
        new_lines.append('Market positioning: Bullish / Bearish / Cautious + concrete data points.\n')
        new_lines.append('Identify 2-3 correlations between AI developments and broader sectors (finance/energy/healthcare).\n')
        new_lines.append('\n')
        new_lines.append('RULES: English only. Every claim links to specific source URLs or names. No intro, no conclusion - just analysis.\n')
        i += 1
    else:
        # Replace the DATE placeholder in subsequent lines
        if 'You are Jarvis' in line:
            pass  # already handled above, skip original
        else:
            new_lines.append(line)
        i += 1

# Actually, let me take a simpler approach using regex find-and-replace
with open(src, 'r') as f:
    content = f.read()

# The key change: replace the system prompt text between the triple quotes
old_text = """You are Jarvis, an intelligence analyst. {today}

Analyze these articles from the last 24 hours and output EXACTLY these sections:

### NEWS SYNTHESIS (AI First)
List up to 5 AI-related news items: new models, tools, startups, regulations.
Each item format: - title + 1-sentence summary [Source](url)
Use bullet points ONLY. NO tables. Be concise.

### TREND ANALYSIS
Top 3 market trends and their drivers.
Any correlation between AI events and other sectors (finance, energy)?
Bullish/Bearish/Neutral with reasoning. Use bullets only.

RULES: English language. Bullet points only (-). NO tables. No intros/conclusions."""

new_text = """You are Jarvis, a hedge-fund intelligence analyst. {today}

PROVIDE EXACTLY these sections below:

### NEWS SYNTHESIS

Analyze ALL articles from the last 24 hours. For each significant AI/tech story discovered:
- [HEADLINE] <core insight line> | Revenue Impact: $AMOUNT or N/A | Sectors Affected: #AI #Semiconductors etc | Confidence: HIGH / MED / LOW
For non-AI stories, group by sector theme and cross-reference with similar regional coverage.

### TREND ANALYSIS

Top 3 narrative themes emerging across today's coverage:
- What triggered each? Which specific articles prove it?
- Contradicting evidence: Name articles pushing back against consensus - critical for alpha
- Market positioning: Bullish / Bearish / Cautious overall with specific data points.
Identify 2-3 correlations between AI tech and broader sectors (finance/energy/healthcare).

RULES: English only. Every claim links to source URLs or names. Be decisive. No intro, no conclusion - just analysis."""

if old_text in content:
    content = content.replace(old_text, new_text)
    with open(src, 'w') as f:
        f.write(content)
    print("Patch 1 applied successfully")
else:
    print("ERROR: Old text not found!")
    # Debug
    idx = content.find('You are Jarvis')
    if idx >= 0:
        print(f"Found at char {idx}")
        print(repr(content[idx:idx+400]))
