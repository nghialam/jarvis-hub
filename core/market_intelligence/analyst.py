"""
analyst.py - Stage 3: Analysis (Analyst Agent)

LLM-powered analysis of each article: generate summary + classify sentiment.
Uses ollama_client for LLM inference.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger(__name__)


# Analyst Agent prompt template
ANALYST_PROMPT_TEMPLATE = """You are a Lead Market Intelligence Agent analyzing financial news.

Title: {title}
Date: {date}
URL: {url}
Content: {content}

Return ONLY valid JSON (no markdown, no explanation, no code blocks):
{{
          "title": "{title}",
           "date": "{date}",
           "url": "{url}",
           "summary": "Concise summary in 1-3 sentences. Professional tone.",
           "sentiment": "Bullish" | "Bearish" | "Neutral"
}}

- If impact is unclear, mark sentiment as "Neutral" with note "Insufficient information to determine sentiment."
- Maintain strict factual accuracy - do not hallucinate data.
- Summary must be <=3 sentences.
- Sentiment should reflect expected market impact (up/down/neutral).
"""


def _analyze_single_article(article):
        """Analyze a single article using LLM.

            Args:
                article: Cleaned article dict with clean_content key

            Returns:
                Dict with title, date, url, summary, sentiment
        """
        title = article.get("title", "Untitled")
        date = article.get("date", "")
        url = article.get("url", "")
        content = article.get("clean_content", article.get("content", ""))

          # Build prompt
        prompt = ANALYST_PROMPT_TEMPLATE.format(
            title=title,
            date=date,
            url=url,
            content=content[:3000]      # Cap content length
          )

          # Call LLM
        try:
            from core.ollama_client import ollama_parse_json
            result = ollama_parse_json(prompt, timeout=180)

            if result and isinstance(result, dict):
                  # Validate required fields
                if "summary" in result and "sentiment" in result:
                    result["title"] = title
                    result["date"] = date
                    result["url"] = url
                    log.debug(f"[MI][{article.get('source', '?')}] Analyzed: {result['sentiment']}")
                    return result

                  # If LLM returns malformed response, use fallback
            log.warning(f"[MI] Malformed LLM response for: {title[:50]}")
            return _fallback_analysis(title, date, url, content)

        except Exception as e:
            log.error(f"[MI] LLM analysis failed for {title[:50]}: {e}")
            return _fallback_analysis(title, date, url, content)


def _fallback_analysis(title, date, url, content):
        """Fallback analysis when LLM is unavailable.

            Uses heuristic sentiment matching from news_engine.py patterns.
        """
          # Heuristic sentiment patterns (from news_engine.py)
        BULLISH = ["tăng", "lãi", "khởi sắc", "bùng nổ", "vượt", "lợi nhuận", "doanh thu",
                     "phục hồi", "mở rộng", "đầu tư", "tốt", "bứt phá", "tích lũy",
                     "mua ròng", "đón sóng", "hứng thú", "năng lực", "đột phá",
                     "surge", "gain", "rise", "bullish", "optimistic", "growth", "profit"]

        BEARISH = ["giảm", "rớt", "sụt giảm", "thất bại", "thua lỗ", "rủi ro", "suy giảm",
                     "rơi tự do", "phá sản", "sụp đổ", "căng thẳng", "suy thoái", "sổ lỗ",
                     "nợ", "bất ổn", "khủng hoảng", "đình chỉ", "bán tháo", "rút vốn",
                     "áp lực giảm", "rơi sâu", "sập", "thắt chặt", "tăng nợ",
                     "crash", "fall", "drop", "bearish", "pessimistic", "decline", "loss"]

        text = (title + " " + content).lower()
        bull_count = sum(1 for p in BULLISH if p in text)
        bear_count = sum(1 for p in BEARISH if p in text)

        if bull_count > bear_count + 2:
            sentiment = "Bullish"
        elif bear_count > bull_count + 2:
            sentiment = "Bearish"
        else:
            sentiment = "Neutral"

          # Create brief summary from title + first sentence
        summary = title
        if content:
            first_sentence = content.split(".")[0][:150]
            if first_sentence and len(first_sentence) > 20:
                summary = f"{title}. {first_sentence}..."

        return {
              "title": title,
              "date": date,
              "url": url,
              "summary": summary,
              "sentiment": sentiment,
              "_fallback": True,      # Mark as heuristic-based
          }


def analyze_articles(articles):
        """Analyze multiple articles in parallel using LLM.

            Args:
                articles: List of cleaned article dicts

            Returns:
                List of analyzed article dicts with summary and sentiment
        """
        if not articles:
            return []

        log.info(f"[MI] Starting analysis for {len(articles)} articles...")

        analyzed = []
        failed = 0

          # Process in parallel (max 4 concurrent LLM calls to avoid overload)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_analyze_single_article, art): art for art in articles}

            for future in as_completed(futures):
                try:
                    result = future.result(timeout=90)
                    if result:
                        analyzed.append(result)
                except Exception as e:
                    art = futures[future]
                    log.error(f"[MI] Article analysis failed: {art.get('title', '?')}: {e}")
                    failed += 1

        log.info(f"[MI] Analysis complete: {len(analyzed)} succeeded, {failed} failed")
        return analyzed
