"""
LLM Evaluation Pipeline for Jarvis Hub - Tier 2 Auto-Analysis

Uses Qwen3.6:35b-a3b-mxfp8 via Ollama to analyze market data and generate
Vietnamese-language trading insights, sentiment analysis, and strategy briefs.

Usage:
    python3 llm_evaluation.py [--dry-run]
    
Outputs:
    - /Users/nghialam/jarvis-hub/evaluations/latest_evaluation.json (preview)
    - INSERTS into jarvis_market.db::llm_evaluations table
"""

import json
import os
import re
import sys
import sqlite3
import time
import requests
from datetime import date, datetime


# Configuration
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "jarvis_market.db")
EVALUATION_JSON = os.path.join(
    os.path.dirname(__file__),
    "..", "evaluations", "latest_evaluation.json"
)
OLLAMA_URL = "http://localhost:11434"
LLM_MODEL = "qwen3.6:35b-a3b-mxfp8"

os.makedirs(os.path.dirname(EVALUATION_JSON), exist_ok=True)


# ---------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------

def fetch_market_overview():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM daily_prices WHERE symbol='VN-INDEX' "
            "ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return [dict(row)] if row else []
    except Exception as e:
        print(f"[WARN] fetch_market_overview: {e}")
        return []
    finally:
        conn.close()


def fetch_latest_signals():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        for table in ["signals", "jarvis_signals"]:
            try:
                row = conn.execute(
                    f"SELECT * FROM {table} ORDER BY date DESC LIMIT 50"
                ).fetchall()
                if row:
                    return [dict(r) for r in row]
            except Exception:
                continue
        return []
    except Exception as e:
        print(f"[WARN] fetch_latest_signals: {e}")
        return []
    finally:
        conn.close()


def fetch_ollama_status():
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        data = resp.json()
        models = [m.get("name") for m in data.get("models", [])]
        return {"running": True, "models": models}
    except Exception:
        return {"running": False, "models": []}


# ---------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------

def build_evaluation_prompt(market_data, signals):
    today = date.today().isoformat()

    # Market section
    mkt_lines = []
    if market_data:
        for row in market_data:
            sym = row.get("symbol", "?")
            dt = row.get("date", "")
            close = row.get("close", "?")
            chg = row.get("change_percent", "N/A")
            vol = row.get("volume", "N/A")
            mkt_lines.append(
                f"- **{sym}** ({dt}): giá {close}, thay đổi {chg}%, "
                f"vol: {vol}"
            )
    else:
        mkt_lines.append("_Chưa có dữ liệu._")

    # Signals section
    sig_lines = []
    if signals:
        for s in signals[:10]:
            sym = s.get("symbol", "?")
            rec = s.get("recommendation", s.get("signal", "?"))
            conf = s.get("confidence_percent", "?")
            reason = s.get("reason", s.get("analysis_text", ""))[:100]
            sig_lines.append(
                f"- **{sym}**: {rec} ({conf}% confident) "
                f"_{reason}_..."
            )
    else:
        sig_lines.append("_Chưa có tín hiệu mới._")

    ollama = fetch_ollama_status()
    oll_text = (
        f"- Ollama: {'OK' if ollama['running'] else 'DOWN'} | "
        f"Models: {', '.join(ollama.get('models', []))}"
    )

    prompt = f"""Bạn là nhà phân tích chứng khoán VN chuyên nghiệp,
15 năm kinh nghiệm. Hôm nay {today}.

## THỊ TRƯỜNG
{chr(10).join(mkt_lines)}

## TÍN HIỆU
{chr(10).join(sig_lines)}

## OLLAMA STATUS
{oll_text}

HAY PHÂN TÍCH:
1. Xu hướng tổng quan thị trường (tăng/giảm/biến động) so với gần nhất
2. Đánh giá 3-5 tín hiệu mạnh nhất, cảnh báo rủi ro
3. Đề xuất hành động: 2-3 khuyến nghị mua/bán/giữ + stop-loss
4. Cảm xúc toàn bộ: 📈Tích cực / 📉Tiêu cực / ➖Trung lập -- [1 dòng]

Viết tiếng Việt tự nhiên, chuyên nghiệp, bullet point ngắn gọn."""

    return prompt


# ---------------------------------------------------------------
# Call Ollama (streaming)
# ---------------------------------------------------------------

def call_ollama(prompt, max_retries=2):
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system",
             "content": "Bạn là nhà phân tích CK VN 15 năm kinh nghiệm."},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "options": {"num_predict": 4096, "temperature": 0.7, "top_p": 0.9},
    }

    for attempt in range(1, max_retries + 1):
        print(f" [LLM] Attempt {attempt}/{max_retries}...")
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=300,
                stream=True,
            )

            if resp.status_code != 200:
                print(f" [LLM] HTTP {resp.status_code}: "
                      f"{resp.text[:200]}")
                continue

            full_text = ""
            for line in resp.iter_lines():
                if not line or not line.strip():
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                    delta_msg = chunk.get("message", {})
                    content = delta_msg.get("content", "")

                    # Fallback for some models that use 'delta' directly
                    if not content and "delta" in chunk:
                        print(f" [LLM] Using 'delta' field")

                    full_text += content

                except json.JSONDecodeError as e:
                    print(f"[LLM] JSON parse error: {e}, skipping line")

            if full_text.strip():
                return full_text.strip()

        except requests.exceptions.ConnectionError:
            print("[LLM] Connection refused. Is Ollama running?")
            time.sleep(3)
        except requests.exceptions.Timeout:
            print("[LLM] Timeout after 5 minutes")
            if attempt < max_retries:
                time.sleep(2)

    return None


# ---------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------

def analyze_sentiment(text, _sentiment_str):
    pos = len(re.findall(r"\+[^\n]+\n", text))
    neg = len(re.findall(r"\-[^\n]+\n", text))

    score = pos - neg if (pos + neg) > 0 else 0

    if score >= 2:
        sentiment = "TICH_CUC"
    elif score <= -1:
        sentiment = "BIET_CHU"
    else:
        sentiment = "TRUNG_LAP"

    return sentiment, score


# ---------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------

def main():
    today_str = date.today().isoformat()

    print("\n[STEP 1] Loading market data from jarvis_market.db...")
    try:
        market_data = fetch_market_overview()
        signals = fetch_latest_signals()
        print(f" Found {len(market_data)} market, "
              f"{len(signals)} signal records")
    except Exception as e:
        print(f"[ERROR] Loading data: {e}")
        return

    print("[STEP 2] Building LLM evaluation prompt...")
    try:
        prompt = build_evaluation_prompt(market_data, signals)
        print(f" Prompt: {len(prompt)} chars, "
              f"~{len(prompt.split())} words")
    except Exception as e:
        print(f"[ERROR] Building prompt: {e}")
        return

    print("[STEP 3] Calling Qwen3.6 via Ollama...")
    result = call_ollama(prompt)

    if not result:
        print("[WARN] No LLM output -- pipeline finished. "
              "Check ollama logs.")
        return

    print("[STEP 4] Analyzing sentiment...")
    try:
        sentiments = {}
        scores = []
        for r in result.split("\n"):
            if "+" in r:
                sentiments["+", r.strip()] = True
            if "-" in r and not r.startswith("-Ollama"):
                sentiments["-", r.strip()] = True

        pos = sum(1 for k in sentiments if k == "+")
        neg = sum(1 for k in sentiments if k == "-")
        score = pos - neg if (pos + neg) > 0 else 0

        if score >= 2:
            sentiment = "TICH_CUC"
        elif score <= -1:
            sentiment = "BIET_CHU"
        else:
            sentiment = "TRUNG_LAP"

        print(f" Sentiment: {sentiment} (score: {score:+d})")

        # Save preview JSON
        os.makedirs(os.path.dirname(EVALUATION_JSON), exist_ok=True)
        with open(EVALUATION_JSON, 'w', encoding='utf-8') as f:
            json.dump({
                "date": today_str,
                "timestamp": datetime.now().isoformat(),
                "sentiment": sentiment,
                "score": score,
                "evaluation_preview": result[:500],
            }, f, ensure_ascii=False, indent=2)
        print(f" Saved preview to {EVALUATION_JSON}")

    except Exception as e:
        print(f"[WARN] Saving JSON: {e}")

    # Save to DB (optional, skip on DB err)
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS llm_evaluations ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " evaluation_date TEXT,"
            " evaluation_type TEXT DEFAULT 'auto',"
            " content TEXT,"
            " timestamp TEXT"
            ")"
        )
        conn.execute(
            "INSERT INTO llm_evaluations "
            "(evaluation_date, evaluation_type, content, timestamp) "
            "VALUES (?,?,?,?)",
            (today_str, "auto", result[:2000], today_str))
        conn.commit()
        conn.close()
        print(" Saved to jarvis_market.db:: llm_evaluations")
    except Exception as e:
        print(f"[WARN] DB save: {e}")

    # Final summary
    print("\n" + "=" * 50)
    print(" PIPELINE COMPLETE")
    print("=" * 50)
    print(f"Date:          {today_str}")
    print(f"Evaluation:    {len(result)} chars")
    print(f"Market data:   {'OK' if market_data else 'NONE'} "
          f"({len(market_data)} records)")
    print("=" * 50)


if __name__ == "__main__":
    main()
