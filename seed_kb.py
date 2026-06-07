"""
seed_kb.py -- Seed knowledge base with Investopedia-style entries
"""
import sys
sys.path.insert(0, ".")
from core.db import Database

db = Database()

entries = [
    {
        "term": "P/E Ratio",
        "content": "Price-to-Earnings (P/E) ratio là chỉ số đo lường mối quan hệ giữa giá chứng khoán và thu nhập trên mỗi cổ phiếu (EPS). Công thức: P/E = Giá cổ phiếu / EPS. P/E cao cho thấy nhà đầu tư kỳ vọng tăng trưởng tương lai cao, hoặc cổ phiếu đang bị định giá đắt. P/E thấp có thể báo hiệu cổ phiếu bị định giá rẻ hoặc doanh nghiệp gặp khó khăn.",
        "tags": "valuation, fundamental analysis"
    },
    {
        "term": "RSI",
        "content": "Relative Strength Index (RSI) là chỉ báo động lượng oscillator đo lường tốc độ và thay đổi của biến động giá trong khoảng 0-100. RSI > 70 được coi là quá mua (overbought) - tín hiệu bán hoặc chốt lời. RSI < 30 là quá bán (oversold) - tín hiệu mua hoặc bắt đáy. Kỳ phổ biến nhất là 14 ngày.",
        "tags": "technical analysis, indicator, oscillator"
    },
    {
        "term": "MACD",
        "content": "Moving Average Convergence Divergence (MACD) là chỉ báo xu hướng + động lượng. Công thức: MACD line = EMA(12) - EMA(26). Signal line = EMA(9) của MACD line. Histogram = MACD - Signal. Cross qua 0 hoặc signal line là tín hiệu buy/sell. Histogram tăng cho thấy bullish strengthening.",
        "tags": "technical analysis, indicator, trend"
    },
    {
        "term": "SMA",
        "content": "Simple Moving Average (SMA) là đường trung bình động đơn giản, tính bằng cách lấy trung bình cộng giá trong N phiên. SMA(20) = đường ngắn hạn, SMA(50) = trung hạn, SMA(200) = dài hạn. Giá > SMA(200) được coi là bull market, giá < SMA(200) là bear market. Golden cross (SMA50 cắt lên SMA200) là tín hiệu tăng. Death cross thì ngược lại.",
        "tags": "technical analysis, moving average, trend"
    },
    {
        "term": "Candlestick",
        "content": "Mẫu nến (candlestick pattern) dùng để dự đoán xu hướng thị trường dựa trên hình dạng nến. Bullish patterns: Hammer, Bullish Engulfing, Morning Star. Bearish patterns: Shooting Star, Bearish Engulfing, Evening Star. Doji cho thấy phân vân thị trường. Body lớn thể hiện momentum mạnh, bóng dài thể hiện biến động cao.",
        "tags": "technical analysis, price action, pattern"
    },
    {
        "term": "Volume",
        "content": "Khối lượng giao dịch (volume) xác nhận độ tin cậy của xu hướng. Volume tăng kèm giá tăng = trend mạnh. Volume giảm trong uptrend = có thể đảo chiều. Volume spike tại đỉnh đáy thường là tín hiệu reversal. nên kết hợp volume với price action để đánh giá xác suất.",
        "tags": "technical analysis, price action, confirmation"
    },
]

count = 0
for entry in entries:
    existing = db.search_knowledge(entry["term"], limit=1)
    if not existing:
        db.save_term(
            term=entry["term"],
            content=entry["content"],
            tags=entry["tags"]
        )
        count += 1

print("Seeded %d knowledge base entries" % count)
