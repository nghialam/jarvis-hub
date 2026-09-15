"""
core/fallback_engine.py - Heuristic alternatives for all LLM-dependent endpoints

JH3.0 Principle: LLM is always optional. Heuristics provide immediate results.
LLM enhances quality when available, but system never blocks or fails without it.

Endpoints covered:
1. /api/analyze (stock analysis)
2. /api/market-evaluation/generate (market evaluation)
3. /api/v1/news/score (news importance scoring)
4. Market Intelligence pipeline (already has fallbacks in analyst.py + synthesizer.py)
"""

import re
import json
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

log = None


def _get_logger():
    global log
    if log is None:
        try:
            from core.logging_config import get_logger
            log = get_logger("FALLBACK")
        except Exception:
            log = _NullLogger()
    return log


class _NullLogger:
    """No-op logger when logging_config isn't available."""
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


# ============================================================
# 1. Stock Analysis Heuristic (for /api/analyze)
# ============================================================

def analyze_stock_heuristic(symbol: str, market_data: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Generate a stock analysis using technical heuristics without LLM.
    
    Uses price data, calculated indicators, and rule-based logic
    to produce actionable recommendations.
    """
    _get_logger().info("Heuristic analysis for %s", symbol)
    
    if market_data is None:
        market_data = {}
    
    # Extract available price data
    price_data = market_data.get("ohlcv", [])
    if not price_data:
        # No price data at all — return basic heuristic
        return {
            "symbol": symbol,
            "status": "no_data",
            "message": "Khong du lieu gia de phan tich. Can cap nhat du lieu OHLCV truoc.",
            "recommendation": "HOLD",
            "confidence": 0.0,
            "indicators": {"rsi": None, "sma_20": None, "ema_12": None, "ema_26": None, "macd": None, "bb_upper": None, "bb_lower": None},
            "timestamp": datetime.now().isoformat()
        }
    
    # Get last known price
    last_candle = price_data[-1] if isinstance(price_data, list) else market_data.get("last_price", 0)
    current_price = last_candle.get("close", last_candle) if isinstance(last_candle, dict) else last_candle
    
    # Calculate heuristic indicators from available data
    close_prices = []
    if isinstance(price_data, list):
        close_prices = [c.get("close", c) if isinstance(c, dict) else c for c in price_data]
    
    indicators = _calculate_heuristic_indicators(close_prices)
    
    # Generate recommendation based on heuristic rules
    recommendation, confidence, reasoning = _generate_heuristic_recommendation(indicators, current_price, market_data)
    
    return {
        "symbol": symbol,
        "status": "ok",
        "current_price": current_price,
        "recommendation": recommendation,
        "confidence": confidence,
        "indicators": indicators,
        "reasoning": reasoning,
        "generated_by": "heuristic",
        "timestamp": datetime.now().isoformat()
    }


def _calculate_heuristic_indicators(close_prices: List[float]) -> Dict[str, Optional[float]]:
    """Calculate technical indicators from price history using heuristics."""
    if not close_prices:
        return {"rsi": None, "sma_20": None, "ema_12": None, "ema_26": None, "macd": None,
                "bb_upper": None, "bb_lower": None, "volume_trend": None}
    
    n = len(close_prices)
    
    # SMA(20)
    sma_20 = None
    if n >= 20:
        sma_20 = sum(close_prices[-20:]) / 20
    
    # EMA(12) and EMA(26)
    ema_12 = _calculate_ema(close_prices, 12)
    ema_26 = _calculate_ema(close_prices, 26)
    
    # MACD
    macd = None
    if ema_12 is not None and ema_26 is not None:
        macd = ema_12 - ema_26
    
    # RSI (14-period)
    rsi = _calculate_rsi(close_prices, 14)
    
    # Bollinger Bands (20, 2)
    bb_upper = None
    bb_lower = None
    if n >= 20:
        recent_20 = close_prices[-20:]
        mean = sum(recent_20) / 20
        variance = sum((x - mean) ** 2 for x in recent_20) / 20
        std = math.sqrt(variance)
        bb_upper = mean + 2 * std
        bb_lower = mean - 2 * std
    
    return {
        "rsi": round(rsi, 2) if rsi else None,
        "sma_20": round(sma_20, 2) if sma_20 else None,
        "ema_12": round(ema_12, 2) if ema_12 else None,
        "ema_26": round(ema_26, 2) if ema_26 else None,
        "macd": round(macd, 4) if macd else None,
        "bb_upper": round(bb_upper, 2) if bb_upper else None,
        "bb_lower": round(bb_lower, 2) if bb_lower else None
    }


def _calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """Calculate EMA for a list of prices."""
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def _calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Calculate RSI from price history."""
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    # Use full available period for calculation
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _generate_heuristic_recommendation(
    indicators: Dict, current_price: float, market_data: Dict
) -> tuple:
    """Generate buy/sell/hold recommendation based on heuristic rules."""
    score = 0
    reasoning = []
    
    # RSI signal
    rsi = indicators.get("rsi")
    if rsi is not None:
        if rsi < 30:
            score += 3
            reasoning.append("RSI < 30: quá bán, có thể hồi")
        elif rsi < 40:
            score += 1
            reasoning.append("RSI thấp ({}): xu hướng giảm chậm lại".format(rsi))
        elif rsi > 70:
            score -= 3
            reasoning.append("RSI > 70: quá mua, có thể điều chỉnh")
        elif rsi > 60:
            score -= 1
            reasoning.append("RSI cao ({}): đã tăng đáng kể".format(rsi))
    
    # Price vs SMA20
    sma_20 = indicators.get("sma_20")
    if sma_20 and current_price > 0:
        if current_price > sma_20 * 1.05:
            score += 1
            reasoning.append("Giá > SMA20 +5%: trên đường trung bình")
        elif current_price < sma_20 * 0.95:
            score -= 1
            reasoning.append("Giá < SMA20 -5%: dưới đường trung bình")
    
    # MACD signal
    macd = indicators.get("macd")
    if macd is not None:
        if macd > 0:
            score += 1
            reasoning.append("MACD dương: xu hướng tăng")
        else:
            score -= 1
            reasoning.append("MACD âm: xu hướng giảm")
    
    # Bollinger Bands
    bb_upper = indicators.get("bb_upper")
    bb_lower = indicators.get("bb_lower")
    if bb_upper and bb_lower and current_price > 0:
        if current_price >= bb_upper:
            score -= 2
            reasoning.append("Giá chạm BB trên: áp lực giảm")
        elif current_price <= bb_lower:
            score += 2
            reasoning.append("Giá chạm BB dưới: hỗ trợ mạnh")
    
    # Determine recommendation
    if score >= 4:
        recommendation = "STRONG_BUY"
        confidence = min(90, 60 + score * 5)
    elif score >= 2:
        recommendation = "BUY"
        confidence = min(75, 50 + score * 5)
    elif score <= -4:
        recommendation = "STRONG_SELL"
        confidence = min(90, 60 + abs(score) * 5)
    elif score <= -2:
        recommendation = "SELL"
        confidence = min(75, 50 + abs(score) * 5)
    else:
        recommendation = "HOLD"
        confidence = 40 + abs(score) * 5
    
    if not reasoning:
        reasoning = ["Không đủ dữ liệu để đánh giá xu hướng rõ ràng"]
    
    return recommendation, confidence, "; ".join(reasoning)


# ============================================================
# 2. Market Evaluation Heuristic (for /api/market-evaluation/generate)
# ============================================================

def generate_market_evaluation_heuristic(context_data: Dict) -> Dict[str, Any]:
    """
    Generate market evaluation using heuristics without LLM.
    
    Builds a structured market brief from available market data
    using sentiment scoring and trend analysis.
    """
    _get_logger().info("Heuristic market evaluation generated")
    
    parts = []
    sentiment_score = 0
    
    # 1. VN-Indices trend
    vn_indices = context_data.get("vn_indices", {}) or context_data.get("indices", {}).get("vn_indices", {})
    if isinstance(vn_indices, dict):
        for name, info in vn_indices.items():
            if isinstance(info, dict) and "change_pct" in info:
                pct = info.get("change_pct", 0)
                sentiment_score += pct
                arrow = "▲" if pct >= 0 else "▼"
                parts.append(f"{name}: {arrow} {abs(pct):.2f}%")
    
    if not parts:
        parts.append("Khong co du lieu chi so.")
    
    # 2. Crypto trend
    crypto_part = []
    for prefix in ("BTC", "ETH", "SOL"):
        for key, data in context_data.items():
            if key.startswith("crypto_") + prefix and isinstance(data, dict):
                ch = data.get("change_pct", 0)
                sentiment_score += ch * 0.3
                crypto_part.append(f"{prefix}: {'▲' if ch >= 0 else '▼'} {abs(ch):.2f}%")
    
    if crypto_part:
        parts.append(f"Crypto: {', '.join(crypto_part)}")
        sentiment_score += sum(float(d.get("change_pct", 0)) for k, d in context_data.items() if k.startswith("crypto_")) * 0.2
    
    # 3. Gold
    gold = context_data.get("gold", {})
    if isinstance(gold) and "change_pct" in gold:
        pct = gold.get("change_pct", 0)
        parts.append(f"Vang: {'▲' if pct >= 0 else '▼'} {abs(pct):.2f}%")
        sentiment_score += pct * 0.2
    
    # 4. DXY
    dxy = context_data.get("dxy", {})
    if isinstance(dxy) and "change_pct" in dxy:
        dxy_pct = dxy.get("change_pct", 0)
        parts.append(f"DXY: {'▲' if dxy_pct >= 0 else '▼'} {abs(dxy_pct):.2f}%")
        # DXY up = VND down = negative for VN market
        sentiment_score -= dxy_pct
    
    # 5. Oil
    oil = context_data.get("oil", {})
    if isinstance(oil) and "change_pct" in oil:
        parts.append(f"Dau: {'▲' if oil.get('change_pct', 0) >= 0 else '▼'} {abs(oil.get('change_pct', 0)):.2f}%")
    
    # 6. News sentiment
    sent_counts = context_data.get("sentiment_counts", {"positive": 0, "negative": 0, "neutral": 0})
    total = sum(sent_counts.values())
    if total > 0:
        pos_ratio = sent_counts.get("positive", 0) / total
        sentiment_score += (pos_ratio - 0.5) * 10  # normalize to ±5
        parts.append(f"Sentiment tin tuc: +{sent_counts.get('positive', 0)}/{total} positive")
    
    # 7. Overall assessment
    overall_sentiment = "NEUTRAL"
    if sentiment_score > 5:
        overall_sentiment = "BULLISH"
    elif sentiment_score < -5:
        overall_sentiment = "BEARISH"
    elif sentiment_score > 2:
        overall_sentiment = "SLIGHTLY_BULLISH"
    elif sentiment_score < -2:
        overall_sentiment = "SLIGHTLY_BEARISH"
    
    # Build evaluation text
    date = datetime.now().strftime("%Y-%m-%d")
    
    evaluation = (
        f"HOM NAY ({date})\n\n"
        f"TONG QUAN: {overall_sentiment}\n"
        f"Score: {sentiment_score:+.1f}\n\n"
        + "\n".join(parts) +
        f"\n\nKHUYEN NGHI: "
        f"{'Tich luc muc do thap. Theo doi co hoi mua when pullback.' if overall_sentiment in ('BULLISH', 'SLIGHTLY_BULLISH') else 'Giua vung tien. Theo doi rui ro.' if overall_sentiment == 'NEUTRAL' else 'Cat Duc or Giu tien mat. Theo doi rui ro.'}"
    )
    
    summary = evaluation[:300] + "..." if len(evaluation) > 300 else evaluation
    
    return {
        "evaluation": evaluation,
        "summary": summary,
        "sentiment_score": round(sentiment_score, 2),
        "overall_sentiment": overall_sentiment,
        "generated_by": "heuristic",
        "timestamp": datetime.now().isoformat()
    }


# ============================================================
# 3. News Scoring Heuristic (for /api/v1/news/score)
# ============================================================

# Keywords that indicate market-moving importance
CRITICAL_KEYWORDS = [
    # Vietnamese
    "luat", "quy che", "thong tu", "ngan hang nha nuoc", "SBV",
    "lãi suất", "tăng lãi", "giảm lãi", "nong lãi", "inflation", "lạm phát",
    "FDI", "FDI ồ ạt", "đầu tư trực tiếp", "mua lại", "sáp nhập", "merger", "acquisition",
    "IPO", "vốn hóa", "market cap", "marketcap", "xếp hạng", "upboard", "upcom", "hos",
    "khối ngoại", "foreign buying", "nắm giữ", "giao dịch", "khối giao dịch",
    "cạnh tranh", "thị phần", "market share", "doanh thu", "lợi nhuận", "profit", "revenue",
    "phá sản", "suy thoái", "khủng hoảng", "tái cấu trúc",
    # English
    "rate cut", "rate hike", "monetary policy", "fiscal policy", "budget",
    "recession", "growth", "GDP", "inflation rate", "unemployment",
]

MODERATE_KEYWORDS = [
    "nganh", "sector", "industry", "doanh nghiệp", "corp", "company",
    "báo cáo", "report", "kết quả", "result", "earnings",
    "giá", "price", "cạnh tranh", "competition", "chiến lược", "strategy",
    "xu hướng", "trend", "phân tích", "analysis", "dự báo", "forecast",
]

LOW_KEYWORDS = [
    "sự kiện", "event", "giao lưu", "meet", "diễn đàn", "forum", "tuyển dụng",
    "hội nghị", "conference", "ra mắt", "launch", "partnership", "hợp tác",
]


def score_news_heuristic(title: str, summary: str, category: str = "") -> Dict[str, Any]:
    """
    Score news article importance using keyword matching heuristics.
    Returns importance (1-10) and reason.
    """
    text = (title + " " + summary + " " + category).lower()
    score = 5  # Base score
    reasons = []
    
    # Check critical keywords
    critical_count = sum(1 for kw in CRITICAL_KEYWORDS if kw.lower() in text)
    if critical_count >= 3:
        score = min(10, score + 5)
        reasons.append(f"{critical_count} từ khóa quan trọng")
    elif critical_count >= 1:
        score = min(10, score + 3)
        reasons.append(f"{critical_count} từ khóa ảnh hưởng thị trường")
    
    # Check moderate keywords
    moderate_count = sum(1 for kw in MODERATE_KEYWORDS if kw.lower() in text)
    if moderate_count >= 2:
        score = min(10, score + 1)
        reasons.append(f"{moderate_count} từ khóa phân tích")
    
    # Penalty for low-importance patterns
    low_count = sum(1 for kw in LOW_KEYWORDS if kw.lower() in text)
    if low_count >= 2 and critical_count == 0:
        score = max(1, score - 2)
        reasons.append("nội dung sự kiện chung chung")
    
    # Length heuristic: very short = less important
    if len(title) < 30 and len(summary or "") < 50:
        score = max(1, score - 1)
    
    # Cap
    score = max(1, min(10, score))
    
    return {
        "importance": score,
        "reason": "; ".join(reasons) if reasons else "Đánh giá trung bình"
    }


# ============================================================
# 4. LLM Availability Check
# ============================================================

def check_llm_availability() -> Dict[str, Any]:
    """
    Check if LLM is available without blocking.
    Returns status dict compatible with existing llm_client.check_llm_health().
    """
    try:
        # Try importing llm_client
        from core.llm_client import check_llm_health as llm_health_check
        result = llm_health_check()
        result["provider"] = "llm_client"
        return result
    except Exception as e:
        _get_logger().warning("LLM check failed: %s", e)
    
    # Fallback: simple connectivity check
    import socket
    try:
        # Try Ollama (default port 11434)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("localhost", 11434))
        s.close()
        return {"status": "online", "healthy": True, "provider": "ollama_detected"}
    except Exception:
        pass
    
    try:
        # Try omlx (default port 8000)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("localhost", 8000))
        s.close()
        return {"status": "online", "healthy": True, "provider": "omlx_detected"}
    except Exception:
        pass
    
    return {
        "status": "offline",
        "healthy": False,
        "provider": "none",
        "details": "No LLM service detected on localhost:11434 or localhost:8000"
    }
