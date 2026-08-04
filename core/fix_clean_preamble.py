"""Fix replacement of _clean_reasoning_preamble in tier_llm_analyst.py."""
import re

path = "core/tier_llm_analyst.py"

with open(path, "r") as f:
    content = f.read()

# Build the new function as a raw triple-quoted string to avoid escaping issues
new_func = '''def _clean_reasoning_preamble(text):
    """Remove Qwen3.6 chain-of-thought artifacts from streaming output.

    Instead of simple prefix-skip, uses content-based filtering: only paragraphs
    containing substantive Vietnamese-market-analysis signals are kept; everything
    else (self-referential commentary, draft-structuring, meta-instructions) is
    discarded.

    Substantive markers: VN-Index, sector/ticker names, technical analysis verbs
    and nouns (tăng/giảm/dự báo/momentum/củng cố/bullish/....), or economic
    indicators (lãi suất, dòng tiền, vốn FII/FDI....).
    """
    raw = text.split("\\n\\n") if "\\n\\n" in text else [text]
    paras = [p.strip() for p in raw if p.strip()]

    # Patterns that signal reasoning artifacts (meta-commentary, not content)
    ARTIFACT_PATTERNS = [
        "here", "thinking",                  # "here's a thinking process"
        "let me", "i need to",              # task-planning language
        "as an ai",                          # self-reference
        "**role:** financial",               # role-playing preamble
        "draft - section by",               # planning phrasing
        "mental refinement",                 # internal refinement loop
        "let's draft",                       # meta-drafting
        "let me start",                      # task-planning
        "sure,",                             # conversational filler
        "okay,",                             # conversational filler
        "draft generation (mental refinement",
        "check constraints",                 # constraint-checking meta
        "final output draft",               # drafting meta
        "here's the analysis",              # greeting/meta
        "i'll start",                        # planning language
        "reviewing the data",               # reasoning preamble
        "let's refine",                     # self-correction
        "self-correction",                  # self-review artifact
        "structure check",                  # meta-validation
        "will generate",                    # pre-generation meta
        "draft generation in",              # drafting language
        "refine the draft",                 # refinement loop
        "align with provided data",        # planning artifact
        "keeping it tight",                # self-note artifact
        "ensure tone is",                  # meta-instruction
        "i will format",                   # intent statement
    ]

    # Markers that indicate substantive content — at least one must exist to keep
    SUBSTANTIVE_MARKERS = [
        # Market indices & direction
        "vn", "vnei", "hnx", "upcom",
        "index trend", "đỉnh", "mức cao", "tăng", "giảm", "bốc hơi",
        "bullish", "bearish", "tái cấu",
        # Vietnamese sector names
        "bất động sản", "ngân hàng", "công nghệ", "bán lẻ", "năng lượng",
        "real estate", "banking", "technology", "retail", "energy",
        # Technical/economic analysis terms
        "khối lượng", "đáo thuế", "dòng tiền", "vốn fii", "fdi",
        "lãi suất", "chính sách", "vĩ mô", "tâm lý",
        "mua vào", "bán ra", "target", "hỗ trợ", "kháng cự",
    ]

    def is_substantive(para):
        """Check if this paragraph contains substantive market analysis content."""
        lower = para.lower()[:500]
        first_line = para.split("\\n")[0].lower().strip()[:200]

        # Quick rejection: matches artifact pattern?
        for pat in ARTIFACT_PATTERNS:
            if pat in lower:
                return False

        # Numbered reasoning titles -> reject
        if re.match(r"^\\s*\\d+\\.\\s+[\\*]{1,2}\\s*\\w", first_line):
            return False
        if re.match(r"^[A-Z]\\.\\s+[\\*]{1,2}\\s*\\w", first_line):
            return False

        # Must contain at least one substantive marker
        for marker in SUBSTANTIVE_MARKERS:
            if marker.lower() in lower:
                return True

        # Fallback: Vietnamese market keywords as secondary signal
        fallback_kws = [
            "tăng", "giảm", "xu hướng", "phân tích", "dự báo",
            "đỉnh", "kháng cự", "hỗ trợ", "lãi suất", "vốn",
        ]
        return any(kw in lower for kw in fallback_kws)

    good = [p for p in paras if is_substantive(p)]

    # Deduplicate repeated sections (Qwen repeats after re-drafting loops)
    seen_headings = set()
    deduped = []
    heading_re = re.compile(r"##*\\s*\\d+\\.\\s*(.*)")

    for para in good:
        heading_match = heading_re.match(para.split("\\n")[0].strip())
        if heading_match:
            heading_text = heading_match.group(1).lower()[:50]
            if not heading_text or heading_text.startswith("tổng quan"):
                if heading_text in seen_headings:
                    continue
                seen_headings.add(heading_text)
        deduped.append(para)

    result = "\\n\\n".join(deduped).strip()
    return result if result else text

'''

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Find the function start
func_start_pattern = r"^def _clean_reasoning_preamble\(text\):"
match_func = re.search(func_start_pattern, content, re.MULTILINE)
if not match_func:
    print("ERROR: No _clean_reasoning_preamble found")
    raise SystemExit(1)

start_pos = match_func.start()

# Find the next top-level def or class after this function
after_start = match_func.end()
# Search for next 'def ' at indentation level 0
next_match = re.search(r'^(?:def |class )', content[after_start:], re.MULTILINE)
if next_match:
    end_pos = after_start + next_match.start()
else:
    end_pos = len(content)

old_func_text = content[start_pos:end_pos]

# Replace
new_content = content[:start_pos] + new_func + content[end_pos:]

if new_content == content:
    print("NO CHANGE DETECTED")
else:
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"OK Function replaced at position {start_pos}")
    # Verify old was gone and new is present
    assert new_func.strip() in new_content, "New function not found in output"
    assert old_func_text == content[start_pos:end_pos], "Old text mismatch at replacement site"
    print("Verified: replacement successful, old function removed")
