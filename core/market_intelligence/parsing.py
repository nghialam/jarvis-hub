"""
parsing.py - Stage 2: Parsing

Clean raw article content for LLM consumption.
Strips HTML tags, removes boilerplate, normalizes text.
"""

import logging
import re

log = logging.getLogger(__name__)


def clean_article(article):
    """Clean a single article's content for LLM consumption.

    Args:
        article: dict with keys: title, date, url, content, source, lang

    Returns:
        Cleaned article dict with 'clean_content' key added
    """
    if not article:
        return article

    original_content = article.get("content", "") or ""

    # Extract clean text
    clean_text = extract_text_from_html(original_content)

    # Normalize whitespace
    clean_text = normalize_text(clean_text)

    # Truncate to LLM context limit (3000 chars for safety)
    if len(clean_text) > 3000:
        clean_text = clean_text[:3000] + "\n\n[...truncated...]"

    article["clean_content"] = clean_text
    article["content_length"] = len(clean_text)

    log.debug(f"[MI][{article.get('source', '?')}] Cleaned: {len(original_content)} -> {len(clean_text)} chars")
    return article


def extract_text_from_html(html):
    """Extract plain text from HTML, removing scripts, styles, nav, ads.

    Args:
        html: Raw HTML string

    Returns:
        Cleaned text string
    """
    if not html or len(html) < 10:
        return html  # Return as-is if too short (might already be plain text)

    # Try BeautifulSoup first
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()

        # Remove ads and sidebars by class name
        for element in soup.find_all(True):
            classes = element.get("class", [])
            if isinstance(classes, list):
                class_str = " ".join(classes).lower()
                if any(kw in class_str for kw in ["ad-", "sidebar", "banner", "nav-", "widget", "related"]):
                    element.decompose()

        # Try to find main content area
        main = soup.find("article") or soup.find("main") or soup.find("div", class_=re.compile(r"(content|article|post-body)"))

        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        return _clean_whitespace(text)

    except ImportError:
        log.debug("[MI] BeautifulSoup not available, using regex fallback")
        return _regex_extract(html)
    except Exception as e:
        log.warning(f"[MI] BeautifulSoup extraction failed: {e}, using regex fallback")
        return _regex_extract(html)


def _regex_extract(html):
    """Fallback: extract text using regex patterns."""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)
    # Clean whitespace
    return _clean_whitespace(text)


def normalize_text(text):
    """Normalize whitespace and encoding.

    - Multiple spaces -> single space
    - Multiple newlines -> double newline (paragraph break)
    - Ensure UTF-8 safe
    """
    if not text:
        return ""

    # Normalize whitespace
    text = re.sub(r"[^\S\n]+", " ", text)  # Single spaces (preserve newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)  # Max 2 consecutive newlines
    text = text.strip()

    # Remove common boilerplate phrases
    boilerplate_patterns = [
        r"\bRead more\b.*$",
        r"\bShare this\b.*$",
        r"\bClick to share\b.*$",
        r"\bLeave a comment\b.*$",
        r"\bPost navigation\b.*$",
        r"\bRelated Posts\b.*",
        r"\bProudly powered by\b.*$",
        r"\bTheme by\b.*",
    ]

    for pattern in boilerplate_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)

    return _clean_whitespace(text)


def _clean_whitespace(text):
    """Clean up whitespace in text."""
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]  # Remove empty lines
    return "\n".join(lines)
